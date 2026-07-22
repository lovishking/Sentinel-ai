"""Incident Report Generator — Phase F

Auto-generates markdown postmortem reports from incident data,
investigation results, fix details, and PR links.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.domain import AgentRun, Evidence, Fix, Incident, PullRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ground truth for archetype evaluation
# ---------------------------------------------------------------------------

ARCHETYPE_GROUND_TRUTH = {
    "crash_loop": {
        "title_keywords": ["crash", "auth"],
        "expected_root_cause_keywords": [
            "none", "nonetype", "null", "attributeerror", "user",
            "process_user", "not found",
        ],
        "file": "auth_service.py",
        "bug_type": "NoneType dereference",
    },
    "latency_spike": {
        "title_keywords": ["latency", "billing"],
        "expected_root_cause_keywords": [
            "n+1", "loop", "query", "slow", "latency",
            "calculate_total_billing", "get_user_balance",
        ],
        "file": "billing_service.py",
        "bug_type": "N+1 query",
    },
    "oom": {
        "title_keywords": ["oom", "worker", "memory"],
        "expected_root_cause_keywords": [
            "unbounded", "cache", "memory", "leak", "global_cache",
            "eviction", "oom", "append",
        ],
        "file": "worker.py",
        "bug_type": "Unbounded cache growth",
    },
}


def _detect_archetype_from_title(title: str) -> Optional[str]:
    """Map an incident title to its archetype key."""
    title_lower = title.lower()
    for archetype, gt in ARCHETYPE_GROUND_TRUTH.items():
        if any(kw in title_lower for kw in gt["title_keywords"]):
            return archetype
    return None


def _is_root_cause_correct(root_cause: str, archetype: str) -> bool:
    """Check if the identified root cause matches ground truth keywords."""
    if archetype not in ARCHETYPE_GROUND_TRUTH:
        return False
    gt = ARCHETYPE_GROUND_TRUTH[archetype]
    rc_lower = root_cause.lower()
    # Require at least 2 keyword matches to count as correct
    matches = sum(1 for kw in gt["expected_root_cause_keywords"] if kw in rc_lower)
    return matches >= 2


def _get_investigation(db: Session, incident_id: int) -> dict:
    """Fetch latest RootCauseSynthesizer output."""
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.incident_id == incident_id,
            AgentRun.agent_name == "RootCauseSynthesizer",
        )
        .order_by(AgentRun.completed_at.desc())
        .first()
    )
    return run.output if run and run.output else {}


def _get_triage(db: Session, incident_id: int) -> dict:
    """Fetch latest TriageAndAnalysis output."""
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.incident_id == incident_id,
            AgentRun.agent_name == "TriageAndAnalysis",
        )
        .order_by(AgentRun.completed_at.desc())
        .first()
    )
    return run.output if run and run.output else {}


def _get_latest_fix(db: Session, incident_id: int) -> Optional[Fix]:
    """Fetch the latest fix for an incident."""
    return (
        db.query(Fix)
        .filter(Fix.incident_id == incident_id)
        .order_by(Fix.created_at.desc())
        .first()
    )


def _get_latest_pr(db: Session, fix_id: int) -> Optional[PullRequest]:
    """Fetch the latest PR for a fix."""
    return (
        db.query(PullRequest)
        .filter(PullRequest.fix_id == fix_id)
        .order_by(PullRequest.created_at.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(db: Session, incident: Incident) -> str:
    """Generate a markdown postmortem report for the incident.

    Returns the full markdown string.
    """
    investigation = _get_investigation(db, incident.id)
    triage = _get_triage(db, incident.id)
    fix = _get_latest_fix(db, incident.id)
    pr = _get_latest_pr(db, fix.id) if fix else None

    root_cause = investigation.get("root_cause", "Not determined")
    confidence = investigation.get("confidence_score", 0.0)
    reasoning = investigation.get("reasoning", "N/A")
    supporting = investigation.get("supporting_evidence", [])
    incident_type = triage.get("incident_type", "unknown")
    error_sig = triage.get("error_signature", "N/A")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # --- Build report ---
    report = f"""# 📋 Incident Postmortem Report

**Incident:** {incident.title} (ID: {incident.id})
**Severity:** {incident.severity or 'N/A'}
**Status:** {incident.status.value if hasattr(incident.status, 'value') else incident.status}
**Generated:** {now}

---

## 🕐 Timeline

| Time | Event |
|------|-------|
| {_fmt_dt(incident.created_at)} | Incident detected — {incident.title} |
"""

    # Add evidence timeline
    for ev in sorted(incident.evidence, key=lambda e: e.created_at):
        source = ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)
        snippet = ev.raw_content[:120].replace("\n", " ")
        report += f"| {_fmt_dt(ev.created_at)} | **[{source.upper()}]** {snippet} |\n"

    # Add investigation/fix/PR milestones
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.incident_id == incident.id)
        .order_by(AgentRun.started_at)
        .all()
    )
    for run in runs:
        report += f"| {_fmt_dt(run.started_at)} | Agent `{run.agent_name}` completed |\n"

    if fix:
        report += f"| {_fmt_dt(fix.created_at)} | Fix generated (status: {fix.status}) |\n"
    if pr:
        report += f"| {_fmt_dt(pr.created_at)} | PR opened: [#{pr.pr_number}]({pr.pr_url}) |\n"

    report += f"""
---

## 🔍 Root Cause Analysis

**Incident Type:** {incident_type}
**Error Signature:** {error_sig}
**Root Cause:** {root_cause}
**Confidence Score:** {confidence:.0%}

### Reasoning
{reasoning}

### Supporting Evidence
"""
    if supporting:
        for i, ev in enumerate(supporting, 1):
            report += f"{i}. {ev}\n"
    else:
        report += "_No supporting evidence citations._\n"

    # --- Fix Summary ---
    report += "\n---\n\n## 🔧 Fix Summary\n\n"
    if fix:
        test_results = fix.test_results or {}
        pytest_res = test_results.get("pytest", {})
        attempts = test_results.get("attempts", "?")
        test_status = "✅ PASSED" if pytest_res.get("returncode") == 0 else "❌ FAILED"

        report += f"**Status:** {fix.status}\n"
        report += f"**Test Results:** {test_status} (attempts: {attempts})\n\n"
        report += f"```diff\n{fix.diff_content}\n```\n"
    else:
        report += "_No fix generated yet._\n"

    # --- PR Link ---
    report += "\n---\n\n## 🔗 Pull Request\n\n"
    if pr:
        report += f"**PR:** [#{pr.pr_number} on {pr.repo}]({pr.pr_url})\n"
        report += f"**Status:** {pr.status}\n"
    else:
        report += "_No PR created yet._\n"

    # --- Footer ---
    report += "\n---\n\n"
    report += "> 🤖 *This report was auto-generated by Sentinel AI.*\n"

    return report


def _fmt_dt(dt: Optional[datetime]) -> str:
    """Format a datetime for the report timeline."""
    if dt is None:
        return "N/A"
    return dt.strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Eval summary
# ---------------------------------------------------------------------------


def get_eval_summary(db: Session) -> dict:
    """Compute evaluation metrics across all synthetic incidents.

    Returns real numbers from actual DB runs:
    - total_incidents: count of synthetic incidents
    - root_cause_accuracy: % where identified root cause matches ground truth
    - average_confidence_score: mean confidence across investigations
    - average_time_to_fix_seconds: mean time from incident creation to fix
    - fix_success_rate: % of fixes with status='applied'
    - per_archetype: breakdown by archetype
    """
    incidents = (
        db.query(Incident)
        .filter(Incident.source_type == "synthetic")
        .all()
    )

    total = len(incidents)
    if total == 0:
        return {
            "total_incidents": 0,
            "root_cause_accuracy": 0.0,
            "average_confidence_score": 0.0,
            "average_time_to_fix_seconds": 0.0,
            "fix_success_rate": 0.0,
            "per_archetype": {},
        }

    correct_count = 0
    confidence_scores = []
    time_to_fix_values = []
    fix_applied_count = 0
    fix_total_count = 0
    archetype_stats: dict[str, dict] = {}

    for incident in incidents:
        archetype = _detect_archetype_from_title(incident.title)
        if archetype is None:
            continue

        # Initialize archetype bucket
        if archetype not in archetype_stats:
            archetype_stats[archetype] = {
                "total": 0,
                "correct": 0,
                "confidence_scores": [],
                "fix_applied": 0,
                "fix_total": 0,
            }
        archetype_stats[archetype]["total"] += 1

        # Check investigation
        inv = _get_investigation(db, incident.id)
        if inv:
            rc = inv.get("root_cause", "")
            conf = inv.get("confidence_score", 0.0)
            confidence_scores.append(conf)
            archetype_stats[archetype]["confidence_scores"].append(conf)

            if _is_root_cause_correct(rc, archetype):
                correct_count += 1
                archetype_stats[archetype]["correct"] += 1

        # Check fix
        fix = _get_latest_fix(db, incident.id)
        if fix:
            fix_total_count += 1
            archetype_stats[archetype]["fix_total"] += 1
            if fix.status == "applied":
                fix_applied_count += 1
                archetype_stats[archetype]["fix_applied"] += 1

            # Time to fix = fix.created_at - incident.created_at
            if fix.created_at and incident.created_at:
                delta = (fix.created_at - incident.created_at).total_seconds()
                time_to_fix_values.append(delta)

    # Compute aggregates
    root_cause_accuracy = (correct_count / total * 100) if total > 0 else 0.0
    avg_confidence = (sum(confidence_scores) / len(confidence_scores)) if confidence_scores else 0.0
    avg_ttf = (sum(time_to_fix_values) / len(time_to_fix_values)) if time_to_fix_values else 0.0
    fix_rate = (fix_applied_count / fix_total_count * 100) if fix_total_count > 0 else 0.0

    # Per-archetype summary
    per_arch = {}
    for arch, stats in archetype_stats.items():
        gt = ARCHETYPE_GROUND_TRUTH.get(arch, {})
        s_scores = stats["confidence_scores"]
        per_arch[arch] = {
            "total_incidents": stats["total"],
            "root_cause_accuracy": (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0.0,
            "average_confidence": (sum(s_scores) / len(s_scores)) if s_scores else 0.0,
            "fix_success_rate": (stats["fix_applied"] / stats["fix_total"] * 100) if stats["fix_total"] > 0 else 0.0,
            "ground_truth_bug": gt.get("bug_type", "unknown"),
        }

    return {
        "total_incidents": total,
        "root_cause_accuracy": round(root_cause_accuracy, 1),
        "average_confidence_score": round(avg_confidence, 3),
        "average_time_to_fix_seconds": round(avg_ttf, 1),
        "fix_success_rate": round(fix_rate, 1),
        "per_archetype": per_arch,
    }
