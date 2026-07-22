"""Fix Generation Agent — Phase D

Takes root-cause analysis output (from the investigation pipeline) and
generates a unified diff that patches the identified bug in sample_repo/.

Workflow:
1. Load investigation context from the latest RootCauseSynthesizer AgentRun.
2. Read the buggy source file.
3. Prompt Gemini to produce a unified diff.
4. Apply the diff in an isolated temp copy of sample_repo/.
5. Run ruff (non-blocking lint check).
6. Run pytest on the archetype test.
7. If pytest fails → feed failure back to Gemini for ONE retry.
8. Persist a Fix row with diff_content, status, test_results.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

import google.generativeai as genai

from app.core.config import settings
from app.models.domain import AgentRun, Fix, Incident

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAMPLE_REPO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "sample_repo")
SAMPLE_REPO_DIR = os.path.normpath(SAMPLE_REPO_DIR)

# Map archetype keywords (found in incident titles) to their test files
ARCHETYPE_TEST_MAP = {
    "crash": "tests/test_auth_service.py",
    "auth": "tests/test_auth_service.py",
    "latency": "tests/test_billing_service.py",
    "billing": "tests/test_billing_service.py",
    "oom": "tests/test_worker.py",
    "worker": "tests/test_worker.py",
}

ARCHETYPE_FILE_MAP = {
    "crash": "auth_service.py",
    "auth": "auth_service.py",
    "latency": "billing_service.py",
    "billing": "billing_service.py",
    "oom": "worker.py",
    "worker": "worker.py",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_gemini_response(prompt: str) -> str:
    """Call Gemini and return the text response."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")
    model = genai.GenerativeModel("gemini-flash-latest")
    response = model.generate_content(prompt)
    return response.text


def _detect_archetype(incident: Incident) -> Optional[str]:
    """Detect which archetype an incident belongs to from its title."""
    title_lower = (incident.title or "").lower()
    for keyword in ARCHETYPE_TEST_MAP:
        if keyword in title_lower:
            return keyword
    return None


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
    if not run or not run.output:
        raise ValueError(
            f"No RootCauseSynthesizer run found for incident {incident_id}. "
            "Run the investigation pipeline first."
        )
    return run.output


def _read_file(path: str) -> str:
    """Read a file and return its contents."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_diff_from_response(response_text: str) -> str:
    """Extract a unified diff block from a Gemini response.

    Looks for fenced code blocks first, then falls back to lines
    starting with --- / +++ / @@ / + / - / space.
    """
    # Try fenced code block (```diff ... ``` or ``` ... ```)
    fenced = re.findall(r"```(?:diff)?\s*\n(.*?)```", response_text, re.DOTALL)
    if fenced:
        return fenced[0].strip()

    # Fallback: collect contiguous diff-like lines
    lines = response_text.splitlines()
    diff_lines: list[str] = []
    in_diff = False
    for line in lines:
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            in_diff = True
        if in_diff:
            diff_lines.append(line)
    if diff_lines:
        return "\n".join(diff_lines)

    raise ValueError("Could not extract a unified diff from the LLM response.")


def _apply_unified_diff(source: str, diff_text: str) -> str:
    """Apply a unified diff to *source* and return the patched text.

    This is a minimal pure-Python implementation that handles the common
    single-hunk case produced by the LLM.  It parses ``@@ -start,count
    +start,count @@`` headers and applies removals / additions.
    """
    source_lines = source.splitlines(keepends=True)
    # Ensure every line has a newline for consistent processing
    if source_lines and not source_lines[-1].endswith("\n"):
        source_lines[-1] += "\n"

    diff_lines = diff_text.splitlines()

    # Collect hunks
    hunks: list[dict] = []
    current_hunk: Optional[dict] = None
    for line in diff_lines:
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                current_hunk = {
                    "src_start": int(match.group(1)),
                    "src_count": int(match.group(2)) if match.group(2) else 1,
                    "lines": [],
                }
                hunks.append(current_hunk)
        elif current_hunk is not None:
            if line.startswith("---") or line.startswith("+++"):
                continue
            current_hunk["lines"].append(line)

    if not hunks:
        raise ValueError("No hunks found in the diff.")

    # Apply hunks in reverse order so line numbers stay valid
    result_lines = list(source_lines)
    for hunk in reversed(hunks):
        start = hunk["src_start"] - 1  # 0-indexed
        # Determine how many source lines this hunk consumes
        remove_lines: list[str] = []
        add_lines: list[str] = []
        for hl in hunk["lines"]:
            if hl.startswith("-"):
                remove_lines.append(hl[1:])
            elif hl.startswith("+"):
                add_lines.append(hl[1:] + "\n")
            elif hl.startswith(" "):
                # Context line — keep in both
                remove_lines.append(hl[1:])
                add_lines.append(hl[1:] + "\n")
            else:
                # Bare line (no prefix) — treat as context
                remove_lines.append(hl)
                add_lines.append(hl + "\n")

        span = len(remove_lines) if remove_lines else hunk["src_count"]
        result_lines[start : start + span] = add_lines

    return "".join(result_lines)


def _build_diff_prompt(
    buggy_source: str,
    file_name: str,
    root_cause: str,
    reasoning: str,
    retry_feedback: Optional[str] = None,
) -> str:
    """Build the Gemini prompt for diff generation."""
    base = f"""\
You are an expert software engineer. You are given a buggy Python source file
and a root-cause analysis. Generate a **unified diff** that fixes the bug.

## Source file: {file_name}
```python
{buggy_source}
```

## Root-cause analysis
{root_cause}

## Reasoning
{reasoning}

## Instructions
1. Output ONLY a valid unified diff (--- a/{file_name} / +++ b/{file_name} with @@ hunk headers).
2. Do NOT include any explanation outside the diff block.
3. The fix must be minimal — change only what is necessary.
4. Wrap the diff in a ```diff ... ``` fenced code block.
"""
    if retry_feedback:
        base += f"""
## Previous attempt failed
The diff you produced earlier was applied and tested, but the tests failed
with the following output. Please fix the diff:
```
{retry_feedback}
```
"""
    return base


def _run_ruff(file_path: str) -> dict:
    """Run ruff on a file. Returns dict with stdout/stderr. Non-blocking."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.stdout.strip() or result.stderr.strip():
            logger.warning("Ruff findings on %s:\n%s%s", file_path, result.stdout, result.stderr)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        logger.warning("ruff not installed — skipping lint check")
        return {"returncode": -1, "stdout": "", "stderr": "ruff not found"}
    except Exception as e:
        logger.warning("ruff error: %s", e)
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def _run_pytest(temp_repo_dir: str, test_file: str) -> dict:
    """Run pytest on a specific test file inside the temp repo copy."""
    test_path = os.path.join(temp_repo_dir, test_file)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=temp_repo_dir,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_fix(db: Session, incident: Incident) -> Fix:
    """Generate a fix for the given incident.

    Returns a persisted Fix object with diff_content, status, and
    test_results populated.
    """
    # 1. Detect archetype
    archetype_key = _detect_archetype(incident)
    if not archetype_key:
        raise ValueError(
            f"Cannot detect archetype from incident title: '{incident.title}'"
        )

    suspect_file = ARCHETYPE_FILE_MAP[archetype_key]
    test_file = ARCHETYPE_TEST_MAP[archetype_key]

    # 2. Load investigation output
    investigation = _get_investigation_output(db, incident.id)
    root_cause = investigation.get("root_cause", "Unknown")
    reasoning = investigation.get("reasoning", "")

    # 3. Read buggy source
    buggy_path = os.path.join(SAMPLE_REPO_DIR, suspect_file)
    if not os.path.isfile(buggy_path):
        raise FileNotFoundError(f"Buggy source file not found: {buggy_path}")
    buggy_source = _read_file(buggy_path)

    # 4. Generate diff (with one retry)
    max_attempts = 2
    diff_content = ""
    test_results: dict = {}
    ruff_results: dict = {}
    status = "needs_human_review"

    retry_feedback: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        logger.info("Fix generation attempt %d/%d for incident %d", attempt, max_attempts, incident.id)

        # --- Generate diff via Gemini ---
        prompt = _build_diff_prompt(
            buggy_source, suspect_file, root_cause, reasoning, retry_feedback
        )
        try:
            raw_response = _get_gemini_response(prompt)
            diff_content = _extract_diff_from_response(raw_response)
        except Exception as e:
            logger.error("Diff generation failed: %s", e)
            test_results = {"error": f"Diff generation failed: {e}"}
            break

        # --- Apply diff in isolated temp copy ---
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="sentinel_fix_")
            shutil.copytree(SAMPLE_REPO_DIR, os.path.join(temp_dir, "sample_repo"))
            temp_repo = os.path.join(temp_dir, "sample_repo")

            patched_file = os.path.join(temp_repo, suspect_file)
            temp_source = _read_file(patched_file)

            try:
                patched_source = _apply_unified_diff(temp_source, diff_content)
            except Exception as e:
                logger.error("Diff apply failed: %s", e)
                retry_feedback = f"Diff could not be applied: {e}"
                test_results = {"error": f"Diff apply failed: {e}"}
                continue

            with open(patched_file, "w", encoding="utf-8") as f:
                f.write(patched_source)

            # --- Ruff lint (non-blocking) ---
            ruff_results = _run_ruff(patched_file)

            # --- Pytest validation ---
            test_results = _run_pytest(temp_repo, test_file)

            if test_results["returncode"] == 0:
                status = "applied"
                logger.info("Tests passed on attempt %d!", attempt)
                break
            else:
                logger.warning(
                    "Tests failed on attempt %d:\n%s",
                    attempt,
                    test_results.get("stdout", ""),
                )
                retry_feedback = (
                    f"STDOUT:\n{test_results.get('stdout', '')}\n\n"
                    f"STDERR:\n{test_results.get('stderr', '')}"
                )
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    # 5. Persist Fix
    fix = Fix(
        incident_id=incident.id,
        diff_content=diff_content,
        status=status,
        test_results={
            "pytest": test_results,
            "ruff": ruff_results,
            "attempts": min(attempt, max_attempts),
        },
        confidence_score=incident.confidence_score,
        created_at=datetime.utcnow(),
    )
    db.add(fix)
    db.commit()
    db.refresh(fix)

    return fix
