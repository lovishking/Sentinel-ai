# 🛡️ Sentinel AI

**Autonomous AI-powered incident resolution platform** that detects,
investigates, fixes, and documents production incidents — end-to-end,
with a single API call per stage.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-purple.svg)]()

---

## Use Cases & Practical Applications

Sentinel AI is designed for SREs, DevOps engineers, and platform teams who want to reduce Mean Time to Resolution (MTTR) for production incidents.

**What it can be used for:**
- **Automated Triage & Root Cause Analysis:** Automatically parses incoming alerts (e.g., from PagerDuty, Datadog), fetches relevant logs and metrics, and uses LLMs to determine the root cause, eliminating manual digging through dashboards.
- **Autonomous Fix Generation:** Proposes code-level fixes to known bug types, tests them in a sandbox, and opens a Pull Request automatically.
- **Incident Postmortems:** Instantly generates detailed incident reports and timelines for team reviews, ensuring nothing falls through the cracks.
- **Knowledge Base Expansion:** Automatically learns from past incidents and resolved PRs, allowing the AI to solve similar future incidents faster.

**How to use it in practice:**
1. **Webhook Integration:** Hook up the `/incidents/simulate` (or a real webhook endpoint) to your alerting system.
2. **Review & Merge:** When an incident fires, the system investigates and opens a GitHub PR. A human engineer reviews the PR, tests it, and merges it.
3. **Observability:** Track the AI's success rate and confidence metrics via the `/eval/summary` endpoint.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Sentinel AI Platform                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌───────────────────────────────────────────┐  │
│  │   FastAPI     │    │        LangGraph Investigation Pipeline   │  │
│  │   REST API    │───▶│                                           │  │
│  │              │    │  ┌─────────┐  ┌─────────┐  ┌───────────┐ │  │
│  │  /simulate   │    │  │ Triage  │─▶│  Code   │─▶│Root Cause │ │  │
│  │  /investigate│    │  │& Analyze│  │ Context │  │Synthesizer│ │  │
│  │  /generate-  │    │  │         │  │  (RAG)  │  │           │ │  │
│  │    fix       │    │  └─────────┘  └─────────┘  └───────────┘ │  │
│  │  /create-pr  │    └───────────────────────────────────────────┘  │
│  │  /report     │                                                   │
│  │  /eval/      │    ┌───────────────────────────────────────────┐  │
│  │   summary    │    │           Fix Generation Agent             │  │
│  └──────────────┘    │                                           │  │
│         │            │  Gemini ──▶ Diff ──▶ Apply in   ──▶ pytest│  │
│         │            │  Prompt     Gen      temp sandbox    test  │  │
│         ▼            │                       ▲                   │  │
│  ┌──────────────┐    │            retry ◀────┘ (if tests fail)   │  │
│  │  PostgreSQL  │    └───────────────────────────────────────────┘  │
│  │  + pgvector  │                                                   │
│  │              │    ┌───────────────────────────────────────────┐  │
│  │  • incidents │    │           GitHub Integration               │  │
│  │  • evidence  │    │                                           │  │
│  │  • agent_runs│    │  Branch ──▶ Commit ──▶ PR ──▶ Label       │  │
│  │  • fixes     │    │  creation   diff      open   by confidence│  │
│  │  • PRs       │    └───────────────────────────────────────────┘  │
│  │  • knowledge │                                                   │
│  │    _chunks   │    ┌───────────────────────────────────────────┐  │
│  │   (vectors)  │    │           Reporting & Eval                 │  │
│  └──────────────┘    │  Postmortem gen │ Root cause accuracy      │  │
│                      │  Timeline       │ Confidence tracking      │  │
│                      │  Fix summary    │ Time-to-fix metrics      │  │
│                      └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘

External Services:
  • Google Gemini API  — LLM for triage, root cause, fix generation
  • GitHub API         — Branch/commit/PR automation (PyGithub)
```

---

## What's Real vs. Synthetic

> **Design choice:** Sentinel AI uses a synthetic evidence layer to
> enable safe, reproducible demos without requiring a live Kubernetes
> cluster. This is an intentional architectural decision — the same
> pipeline works with real observability data.

| Component | Real / Synthetic | Notes |
|---|---|---|
| **Investigation pipeline** | ✅ Real | LangGraph multi-agent with Gemini LLM calls |
| **RAG retrieval** | ✅ Real | pgvector embeddings, L2 similarity search |
| **Fix generation** | ✅ Real | Gemini generates actual diffs, applied & tested |
| **Test validation** | ✅ Real | pytest runs in sandboxed temp copy |
| **GitHub PRs** | ✅ Real | Actual branches, commits, and PRs on GitHub |
| **Eval metrics** | ✅ Real | Computed from actual DB run data |
| **Evidence/incidents** | 🔶 Synthetic | Generated from archetype templates |
| **sample_repo bugs** | 🔶 Synthetic | 3 curated archetypes (crash, latency, OOM) |
| **Past incidents** | 🔶 Seeded | Pre-loaded knowledge base for RAG context |

**The synthetic layer is swappable.** Replace the evidence generator with
a real PagerDuty/Datadog webhook, point `sample_repo/` at a real codebase,
and the rest of the pipeline works unchanged.

---

## Quick Start

### Windows

Start Docker Desktop with Linux containers enabled, then double-click **run.bat** in the project folder. The launcher creates `.env` on first use, builds the stack, and opens the [interactive API docs](http://localhost:8000/docs) after migrations finish and the API responds.

For AI investigations and fix generation, set `GEMINI_API_KEY` in `.env`. For pull request creation, also set `GITHUB_TOKEN` and `GITHUB_REPO` (in `owner/repo` form). Run the launcher again after editing the file.

### From a terminal

Use Docker Compose with support for `up --wait`.

```bash
git clone https://github.com/lovishking/Sentinel-ai.git
cd Sentinel-ai
cp .env.example .env
docker compose up --build --wait --wait-timeout 180
```

Open the [API docs](http://localhost:8000/docs). To see startup errors, run `docker compose logs`. To stop the stack and retain the database, run `docker compose down` in the project folder.

### Run the Demo

See **[DEMO.md](DEMO.md)** for the full step-by-step walkthrough.

Quick version:
```bash
# Seed knowledge base
curl -X POST http://localhost:8000/rag/seed

# Simulate incident
curl -X POST "http://localhost:8000/incidents/simulate?archetype=crash_loop"
# → note the incident ID

# Investigate → Fix → PR → Report
curl -X POST http://localhost:8000/incidents/1/investigate
curl -X POST http://localhost:8000/incidents/1/generate-fix
curl -X POST http://localhost:8000/incidents/1/create-pr    # if GitHub configured
curl http://localhost:8000/incidents/1/report
curl http://localhost:8000/eval/summary
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/incidents/simulate?archetype=` | Create synthetic incident (`crash_loop`, `latency_spike`, `oom`) |
| `GET` | `/incidents` | List all incidents |
| `GET` | `/incidents/{id}` | Get incident details with evidence |
| `POST` | `/rag/seed` | Seed knowledge base with code + past incidents |
| `POST` | `/rag/query` | Query knowledge base (semantic search) |
| `POST` | `/incidents/{id}/investigate` | Run LangGraph investigation pipeline |
| `POST` | `/incidents/{id}/generate-fix` | Generate, test, and store a code fix |
| `POST` | `/incidents/{id}/create-pr` | Open a GitHub PR with the fix |
| `GET` | `/incidents/{id}/report` | Generate postmortem report |
| `GET` | `/eval/summary` | AI observability metrics |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Project Structure & File Details

Here is a detailed breakdown of the repository and the exact purpose of every file:

### Core API & Application Setup (`app/`)
- **`app/api/routes.py`**: Contains all the FastAPI endpoints (the REST API). It exposes routes to simulate incidents, seed the database, trigger investigations, generate fixes, create PRs, and view reports. It acts as the entry point for the frontend or webhooks.
- **`app/core/config.py`**: Manages environment variables and application settings (e.g., database URLs, API keys) using Pydantic. It ensures the app fails fast if required configurations are missing.
- **`app/core/database.py`**: Sets up the SQLAlchemy database engine and session maker. It manages the connection to PostgreSQL.
- **`app/models/domain.py`**: Defines the SQLAlchemy ORM models (database tables) for `Incident`, `Evidence`, `AgentRun`, `Fix`, `PullRequest`, and `KnowledgeChunk`. This is the single source of truth for the database schema.
- **`app/schemas/domain.py`**: Defines the Pydantic models used for API request/response validation. It ensures data entering and leaving the API is strongly typed and formatted correctly.

### AI Services & Business Logic (`app/services/`)
- **`app/services/synthetic_evidence.py`**: Generates fake incidents (crash loops, latency spikes, OOMs) and their associated evidence (logs, metrics). Used to simulate real production outages for testing and demos.
- **`app/services/rag.py`**: Implements the Retrieval-Augmented Generation (RAG) system. It chunks the source code and past incident data, creates vector embeddings using Gemini, and stores them in PostgreSQL (via pgvector) for semantic search during an investigation.
- **`app/services/agent_orchestration.py`**: Configures the LangGraph multi-agent pipeline. It orchestrates the flow from Triage -> Context Retrieval -> Root Cause Synthesis, passing state between different AI agents.
- **`app/services/fix_generation.py`**: The agent responsible for writing code. It uses Gemini to generate a unified diff to fix the identified root cause, applies it in a sandboxed temporary directory, and runs `pytest` and `ruff` to validate the fix.
- **`app/services/github_integration.py`**: Handles GitHub automation using `PyGithub`. It creates feature branches, commits the generated diffs, and opens rich Pull Requests with confidence labels.
- **`app/services/reporting.py`**: Generates Markdown postmortem reports for incidents and calculates evaluation metrics (like root cause accuracy and time-to-fix) across all runs for AI observability.

### Sample Target Repository (`sample_repo/`)
- **`sample_repo/auth_service.py`**: A dummy service containing a synthetic `NoneType` dereference bug (CrashLoopBackOff archetype).
- **`sample_repo/billing_service.py`**: A dummy service containing an N+1 query performance bug (Latency Spike archetype).
- **`sample_repo/worker.py`**: A dummy service containing an unbounded list growth bug (OOM archetype).
- **`sample_repo/tests/`**: Contains `pytest` files for the sample services. The tests are designed to fail on the buggy code and pass once the AI successfully patches the files.

### Infrastructure & Operations
- **`docker-compose.yml`**: Orchestrates the multi-container Docker setup, spinning up the FastAPI server, PostgreSQL (with pgvector), and Redis.
- **`Dockerfile`**: Defines the container image for the FastAPI application, installing system dependencies, Poetry, and the Python packages.
- **`alembic/` & `alembic.ini`**: Manages database schema migrations. Allows upgrading the PostgreSQL database schema as new models are added.
- **`DEMO.md`**: A step-by-step runbook containing copy-paste `curl` commands to demonstrate the platform's capabilities live.
- **`pyproject.toml`**: The Poetry configuration file that defines Python dependencies, project metadata, and development tools (like pytest and ruff).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI, Pydantic v2 |
| LLM | Google Gemini (via `google-generativeai`) |
| Agent Framework | LangGraph (StateGraph) |
| Database | PostgreSQL 15 + pgvector |
| Embeddings | Gemini Embedding API (`gemini-embedding-001`) |
| GitHub | PyGithub (REST API) |
| Testing | pytest, ruff |
| Infrastructure | Docker Compose |

---

## Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# Install dependencies
pip install poetry
poetry install

# Run locally (requires postgres + redis running)
uvicorn app.main:app --reload

# Run tests
pytest tests/ -v
```

---

## License

MIT
