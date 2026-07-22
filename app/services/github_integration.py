"""GitHub Integration Service — Phase E

Creates branches, commits fixes, opens PRs with rich descriptions,
and labels them by confidence tier. Uses PyGithub for all GitHub API
interactions.
"""

import logging
from datetime import datetime
from typing import Optional

from github import Github, GithubException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.domain import AgentRun, Evidence, Fix, Incident, PullRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_github_client() -> Github:
    """Create an authenticated PyGithub client."""
    if not settings.GITHUB_TOKEN:
        raise ValueError(
            "GITHUB_TOKEN is not set. Add it to your .env file with 'repo' scope."
        )
    return Github(settings.GITHUB_TOKEN)


def _get_repo_name() -> str:
    """Return the configured target repo (e.g. 'user/sentinel-sample-repo')."""
    if not settings.GITHUB_REPO:
        raise ValueError(
            "GITHUB_REPO is not set. Add it to your .env file "
            "(e.g. GITHUB_REPO=username/sentinel-sample-repo)."
        )
    return settings.GITHUB_REPO


def _get_investigation_output(db: Session, incident_id: int) -> dict:
    """Fetch the latest RootCauseSynthesizer output for the incident."""
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.incident_id == incident_id,
            AgentRun.agent_name == "RootCauseSynthesizer",
        )
        .order_by(AgentRun.completed_at.desc())
        .first()
    )
    if run and run.output:
        return run.output
    return {}


def _get_code_context(db: Session, incident_id: int) -> list[dict]:
    """Fetch retrieved context from the CodeContext agent run."""
    run = (
        db.query(AgentRun)
        .filter(
            AgentRun.incident_id == incident_id,
            AgentRun.agent_name == "CodeContext",
        )
        .order_by(AgentRun.completed_at.desc())
        .first()
    )
    if run and run.output:
        return run.output.get("retrieved_context", [])
    return []


def _confidence_tier(score: float) -> tuple[str, str]:
    """Return (label_name, emoji_tier) based on confidence score."""
    if score >= 0.8:
        return "high-confidence", "🟢 High"
    else:
        return "needs-review", "🟡 Needs Review"


def _parse_files_from_diff(diff_content: str) -> dict[str, dict]:
    """Parse a unified diff into per-file hunks.

    Returns {filename: {"hunks": [list of hunk strings]}}.
    """
    files: dict[str, dict] = {}
    current_file: Optional[str] = None
    current_lines: list[str] = []

    for line in diff_content.splitlines():
        if line.startswith("+++ b/") or line.startswith("+++ "):
            # Save previous file
            if current_file and current_lines:
                files[current_file] = {"raw_diff": "\n".join(current_lines)}
            # Extract new filename
            fname = line.replace("+++ b/", "").replace("+++ ", "").strip()
            current_file = fname
            current_lines = [line]
        elif line.startswith("--- a/") or line.startswith("--- "):
            current_lines.append(line)
        else:
            current_lines.append(line)

    # Save last file
    if current_file and current_lines:
        files[current_file] = {"raw_diff": "\n".join(current_lines)}

    return files


def _apply_diff_to_content(original: str, diff_text: str) -> str:
    """Apply unified diff hunks to original file content.

    Reuses the same logic as fix_generation._apply_unified_diff
    but imported inline to avoid circular deps.
    """
    from app.services.fix_generation import _apply_unified_diff
    return _apply_unified_diff(original, diff_text)


def _build_pr_body(
    incident: Incident,
    investigation: dict,
    evidence_list: list[Evidence],
    code_context: list[dict],
    fix: Fix,
) -> str:
    """Build the Markdown PR body with full context."""

    root_cause = investigation.get("root_cause", "Unknown")
    confidence = investigation.get("confidence_score", 0.0)
    reasoning = investigation.get("reasoning", "N/A")
    supporting = investigation.get("supporting_evidence", [])
    _, tier_display = _confidence_tier(confidence)

    # --- Root Cause Section ---
    body = f"""## 🔍 Root Cause Analysis

**Incident:** {incident.title} (ID: {incident.id})
**Root Cause:** {root_cause}
**Confidence Score:** {confidence:.0%} ({tier_display})

### Reasoning
{reasoning}

"""

    # --- Supporting Evidence ---
    body += "## 📋 Supporting Evidence\n\n"
    if supporting:
        for i, ev in enumerate(supporting, 1):
            # Truncate long evidence snippets
            snippet = ev[:300] + "..." if len(ev) > 300 else ev
            body += f"{i}. `{snippet}`\n"
    else:
        body += "_No supporting evidence citations available._\n"

    body += "\n### Raw Evidence from Incident\n\n"
    for ev in evidence_list[:5]:  # Cap at 5 to keep PR readable
        source = ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)
        snippet = ev.raw_content[:200] + "..." if len(ev.raw_content) > 200 else ev.raw_content
        body += f"- **[{source.upper()}]** `{snippet}`\n"

    # --- Related Past Incidents ---
    body += "\n## 🔗 Related Past Incidents\n\n"
    if code_context:
        for ctx in code_context:
            source_type = ctx.get("source_type", "")
            content = ctx.get("content", "")[:200]
            distance = ctx.get("distance", 0)
            meta = ctx.get("metadata", {}) or {}
            if source_type == "past_incident":
                incident_id_ref = meta.get("incident_id", "?")
                body += f"- Past Incident #{incident_id_ref}: `{content}` (similarity: {1 - distance:.2f})\n"
            else:
                file_ref = meta.get("file", "unknown")
                body += f"- Code chunk `{file_ref}`: `{content}` (similarity: {1 - distance:.2f})\n"
    else:
        body += "_No related past incidents found._\n"

    # --- Test Results ---
    body += "\n## 🧪 Test Results\n\n"
    test_results = fix.test_results or {}
    pytest_results = test_results.get("pytest", {})
    ruff_results = test_results.get("ruff", {})
    attempts = test_results.get("attempts", "?")

    if pytest_results.get("returncode") == 0:
        body += f"✅ **Tests PASSED** (attempts: {attempts})\n"
    else:
        body += f"❌ **Tests FAILED** (attempts: {attempts})\n"

    if ruff_results.get("returncode") == 0:
        body += "✅ **Ruff lint: clean**\n"
    elif ruff_results.get("returncode", -1) == -1:
        body += "⚠️ **Ruff lint: skipped** (not installed)\n"
    else:
        body += f"⚠️ **Ruff lint: warnings found**\n```\n{ruff_results.get('stdout', '')}\n```\n"

    # --- Diff ---
    body += "\n## 📝 Changes\n\n"
    body += f"```diff\n{fix.diff_content}\n```\n"

    # --- Footer ---
    body += "\n---\n"
    body += "> 🤖 **Generated by Sentinel AI** — human review required\n"

    return body


def _ensure_label(repo, label_name: str, color: str) -> None:
    """Create a label on the repo if it doesn't already exist."""
    try:
        repo.get_label(label_name)
    except GithubException:
        try:
            repo.create_label(name=label_name, color=color)
            logger.info("Created label '%s' on %s", label_name, repo.full_name)
        except GithubException as e:
            logger.warning("Could not create label '%s': %s", label_name, e)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def create_pull_request(db: Session, incident: Incident, fix: Fix) -> PullRequest:
    """Create a GitHub PR for the given fix.

    1. Creates a branch fix/incident-{id}
    2. Commits the patched file(s) via the Contents API
    3. Opens a PR with a rich description
    4. Labels by confidence tier
    5. Persists and returns a PullRequest row
    """
    # --- Validate ---
    repo_name = _get_repo_name()
    gh = _get_github_client()
    repo = gh.get_repo(repo_name)

    if not fix.diff_content:
        raise ValueError("Fix has no diff_content to commit.")

    # --- Gather context for PR body ---
    investigation = _get_investigation_output(db, incident.id)
    evidence_list = list(incident.evidence)
    code_context = _get_code_context(db, incident.id)
    confidence = investigation.get("confidence_score", 0.0)

    # --- Get default branch & its HEAD SHA ---
    default_branch = repo.default_branch
    base_ref = repo.get_git_ref(f"heads/{default_branch}")
    base_sha = base_ref.object.sha

    # --- Create feature branch ---
    branch_name = f"fix/incident-{incident.id}"
    try:
        repo.create_git_ref(
            ref=f"refs/heads/{branch_name}",
            sha=base_sha,
        )
        logger.info("Created branch '%s' on %s", branch_name, repo_name)
    except GithubException as e:
        if e.status == 422:
            # Branch already exists — that's fine, we'll commit on top
            logger.warning("Branch '%s' already exists, reusing.", branch_name)
        else:
            raise

    # --- Commit patched files via Contents API ---
    files_in_diff = _parse_files_from_diff(fix.diff_content)

    if not files_in_diff:
        raise ValueError("Could not parse any files from the diff content.")

    for file_path, file_info in files_in_diff.items():
        # Get current file content from the branch
        try:
            file_obj = repo.get_contents(file_path, ref=branch_name)
            original_content = file_obj.decoded_content.decode("utf-8")
        except GithubException:
            # File doesn't exist on the branch — skip or error
            logger.error("File '%s' not found on branch '%s'", file_path, branch_name)
            raise ValueError(f"File '{file_path}' not found in repo.")

        # Apply diff to get patched content
        patched_content = _apply_diff_to_content(original_content, fix.diff_content)

        # Commit the update
        commit_msg = f"fix: resolve incident #{incident.id} — {incident.title}"
        repo.update_file(
            path=file_path,
            message=commit_msg,
            content=patched_content,
            sha=file_obj.sha,
            branch=branch_name,
        )
        logger.info("Committed patched '%s' to branch '%s'", file_path, branch_name)

    # --- Build PR body ---
    pr_body = _build_pr_body(incident, investigation, evidence_list, code_context, fix)

    # --- Open PR ---
    pr_title = f"🤖 Fix: {incident.title} (Incident #{incident.id})"
    pr = repo.create_pull(
        title=pr_title,
        body=pr_body,
        base=default_branch,
        head=branch_name,
    )
    logger.info("Opened PR #%d on %s: %s", pr.number, repo_name, pr.html_url)

    # --- Label ---
    label_name, _ = _confidence_tier(confidence)
    label_color = "0e8a16" if label_name == "high-confidence" else "fbca04"
    _ensure_label(repo, label_name, label_color)
    pr.add_to_labels(label_name)
    logger.info("Added label '%s' to PR #%d", label_name, pr.number)

    # --- Persist PullRequest row ---
    pr_record = PullRequest(
        fix_id=fix.id,
        repo=repo_name,
        pr_number=pr.number,
        pr_url=pr.html_url,
        status="open",
        created_at=datetime.utcnow(),
    )
    db.add(pr_record)
    db.commit()
    db.refresh(pr_record)

    return pr_record
