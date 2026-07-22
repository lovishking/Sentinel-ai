# 🚀 Sentinel AI — Live Demo Runbook

> **Target time: under 3 minutes end-to-end**
>
> This script walks through the full autonomous incident resolution
> pipeline: detect → investigate → fix → PR → report.

## Prerequisites

```bash
# Ensure the stack is running
docker compose up -d

# Wait for healthy (postgres needs ~5s)
docker compose ps
```

> **Tip:** All commands use `curl`. Replace `localhost:8000` if your
> API is on a different host/port.

---

## Step 1 — Seed the Knowledge Base (~10s)

Loads code chunks from `sample_repo/` and past incident data into the
vector DB for RAG retrieval.

```bash
curl -s -X POST http://localhost:8000/rag/seed | python -m json.tool
```

**Expected:** `{"status": "success", "chunks_added": N, "past_incidents_seeded": 8}`

---

## Step 2 — Simulate an Incident (~1s)

Creates a synthetic `crash_loop` incident with realistic evidence
(logs, metrics, k8s events, deploy info).

```bash
curl -s -X POST "http://localhost:8000/incidents/simulate?archetype=crash_loop" | python -m json.tool
```

**Expected:** An incident with title `"Auth Service CrashLoopBackOff"`,
4 evidence items, status `"open"`.

> 📝 **Note the `id` field** — you'll use it in all subsequent commands.
> Replace `{ID}` below with the actual incident ID.

---

## Step 3 — Run AI Investigation (~15s)

Triggers the LangGraph multi-agent pipeline:
1. **Triage & Analysis** — classifies incident type, extracts error signature
2. **Code Context** — RAG retrieval of relevant code + past incidents
3. **Root Cause Synthesizer** — identifies root cause with confidence score

```bash
curl -s -X POST http://localhost:8000/incidents/{ID}/investigate | python -m json.tool
```

**Expected:** Root cause identifying the `NoneType`/`AttributeError` bug in
`process_user`, confidence ≥ 0.7.

---

## Step 4 — Generate & Validate Fix (~20s)

The fix generation agent:
1. Reads the buggy source file
2. Prompts Gemini to produce a unified diff
3. Applies the diff in an **isolated temp copy** of `sample_repo/`
4. Runs **ruff** lint (non-blocking)
5. Runs **pytest** to validate the fix
6. Retries once if tests fail

```bash
curl -s -X POST http://localhost:8000/incidents/{ID}/generate-fix | python -m json.tool
```

**Expected:** `"status": "applied"`, a valid unified diff adding a
`None` guard to `process_user`, test results showing `returncode: 0`.

---

## Step 5 — Create GitHub PR (~5s)

> ⚠️ **Requires** `GITHUB_TOKEN` and `GITHUB_REPO` in `.env`.
> Skip if not configured — the rest of the demo still works.

```bash
curl -s -X POST http://localhost:8000/incidents/{ID}/create-pr | python -m json.tool
```

**Expected:** A real PR URL on GitHub with:
- Branch `fix/incident-{ID}`
- Rich description with root cause, evidence, test results
- Label `high-confidence` or `needs-review`

---

## Step 6 — View Postmortem Report (~1s)

Auto-generated markdown postmortem with full timeline.

```bash
curl -s http://localhost:8000/incidents/{ID}/report | python -m json.tool
```

**Expected:** Complete postmortem with timeline, root cause analysis,
fix diff, and PR link.

---

## Step 7 — View Eval Summary (~1s)

AI observability metrics computed from real run data.

```bash
curl -s http://localhost:8000/eval/summary | python -m json.tool
```

**Expected:** Real metrics including:
- `total_incidents`: ≥ 1
- `root_cause_accuracy`: percentage matching ground truth
- `average_confidence_score`: from Gemini's analysis
- `fix_success_rate`: percentage of fixes that passed tests
- Per-archetype breakdown

---

## 🎯 Quick Copy-Paste Script

Replace `{ID}` with the incident ID from Step 2:

```bash
# Full pipeline in one block
curl -s -X POST http://localhost:8000/rag/seed | python -m json.tool
curl -s -X POST "http://localhost:8000/incidents/simulate?archetype=crash_loop" | python -m json.tool
# Note the ID, then:
curl -s -X POST http://localhost:8000/incidents/{ID}/investigate | python -m json.tool
curl -s -X POST http://localhost:8000/incidents/{ID}/generate-fix | python -m json.tool
curl -s -X POST http://localhost:8000/incidents/{ID}/create-pr | python -m json.tool
curl -s http://localhost:8000/incidents/{ID}/report | python -m json.tool
curl -s http://localhost:8000/eval/summary | python -m json.tool
```

---

## 💡 Bonus: Run All Three Archetypes

For a more impressive eval summary, run all three bug types:

```bash
curl -s -X POST "http://localhost:8000/incidents/simulate?archetype=crash_loop" | python -m json.tool
curl -s -X POST "http://localhost:8000/incidents/simulate?archetype=latency_spike" | python -m json.tool
curl -s -X POST "http://localhost:8000/incidents/simulate?archetype=oom" | python -m json.tool

# Investigate and fix each (replace IDs)
for ID in {ID1} {ID2} {ID3}; do
  curl -s -X POST http://localhost:8000/incidents/$ID/investigate | python -m json.tool
  curl -s -X POST http://localhost:8000/incidents/$ID/generate-fix | python -m json.tool
done

# Check aggregate metrics
curl -s http://localhost:8000/eval/summary | python -m json.tool
```
