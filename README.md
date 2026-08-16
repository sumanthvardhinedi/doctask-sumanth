# SuperDocs Pre-Submission Filing Validator

Machine-driven filing-package validator. A UI is **not** required.

## Setup

1. Copy `.env.example` to `.env` (never commit `.env`).
2. PostgreSQL with pgvector. Default URL in `.env.example` matches `docker-compose.yml`.
3. Optional SuperDocs stub credentials:

```
SUPERDOCS_BASE_URL=https://api.superdocs.app
SUPERDOCS_API_KEY=your_superdocs_api_key_here
```

Tests run without a live SuperDocs or LLM token. Stage checkpoints store `token_count` / `estimated_cost` as unused (`null`) until a stage actually calls a model. Observability does not invent cost or token totals from that unused state.

```
pip install -r backend/requirements.txt
pytest backend/tests
```

### React review UI (optional)

The UI is **not** required to complete the workflow. You need **two terminals**:

1. API (required): PostgreSQL via `docker compose up -d`, then from `backend/`:

```
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API creates database tables on startup if they are missing.

2. UI from `frontend/`:

```
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to `http://127.0.0.1:8000`. Create a package, add document metadata, validate, and approve/reject findings one at a time. SuperDocs start/decide/export uses the stub client and will fail honestly if the file is not under `UPLOADS_ROOT`.

### MCP (machine interface)

From `backend/`:

```
python -m app.mcp
```

That starts a stdio MCP server with tools for create package, add document, validate/resume, list runs/findings, per-finding decide, observability, and SuperDocs start/decide/export. A UI is not required. Cursor example:

```json
{
  "mcpServers": {
    "filing-validator": {
      "command": "python",
      "args": ["-m", "app.mcp"],
      "cwd": "backend"
    }
  }
}
```

## What exists now

- Create a package and documents over REST
- `POST /api/v1/packages/{id}/validate` starts or resumes the **agent workflow**
- Deterministic validation against indexed Authority A / B rules
- Findings, per-finding approve/reject, SuperDocs review (stub client)

### Agent stages actually executed

`ingest_package` → `classify_documents` → `extract_structure` → `load_authority_rules` → `retrieve_rule_context` → `interpret_rules` → `validate_package` → `generate_findings` → `detect_conflicts` → `human_review` → `superdocs_review` → `finalize_export`

`classify_documents` matches filenames to published `required_document` rules. Unknown names are `insufficient_evidence` (not guessed). Document bytes are not read for classification.

`extract_structure` records persisted metadata and document order. Signature, declaration, dates, and sections are `insufficient_evidence` unless those facts exist on stored metadata. File bytes are not read.

`retrieve_rule_context` uses deterministic indexed-rule lookup (no embeddings). `interpret_rules` restates published description and parameters only.

`validate_package` is the deterministic engine. Extracted signature/declaration values are used only when marked `observed`; missing evidence stays `insufficient_evidence` and is never treated as PASS.

`detect_conflicts` flags when a published signature/declaration rule cannot be established from extraction, or when a PASS finding has no observed evidence. Missing documents stay FAIL findings, not invented conflicts.

Completed stages are checkpointed in Postgres and skipped on resume. `human_review` waits until each reviewable finding (and conflict-mapped finding) has its own approve/reject decision; rejecting one item does not decide the others. After that gate, `superdocs_review` starts the existing SuperDocs upload/chat loop for approved document-backed findings and waits for per-item SuperDocs decisions. `finalize_export` exports only SuperDocs-approved reviews; a rejected SuperDocs item is not exported and does not block unrelated items. Resume with `POST .../validate`, the next approval/SuperDocs decision, or the matching MCP tools. `GET .../agent-workflow` and MCP `get_agent_workflow` report stage status, timing, retries, and SuperDocs operations that were persisted; waiting runs do not report a finished `total_duration_ms`. An optional React review UI lives in `frontend/` and talks to the same REST API.

### REST (machine interface)

- `POST /api/v1/packages`
- `POST /api/v1/packages/{id}/documents`
- `POST /api/v1/packages/{id}/validate`
- `GET /api/v1/packages/{id}/validation-runs`
- `GET /api/v1/packages/{id}/validation-runs/{run}/findings`
- `POST /api/v1/packages/{id}/validation-runs/{run}/findings/{finding}/approval`
- `GET /api/v1/packages/{id}/agent-workflow` — stage status, duration, retries, failures, SuperDocs API operations that actually exist; `token_count` / `estimated_cost` stay `null` unless a stage recorded real usage
- SuperDocs review/decision/export under `/api/v1/packages/{id}/...`
- MCP stdio tools (`python -m app.mcp`) for the same machine flow, including per-finding decide
- `GET /api/v1/packages` and `GET /api/v1/packages/{id}` for the optional React UI

## Limits

- SuperDocs is stub-first unless a real `SUPERDOCS_API_KEY` is configured locally
- Document bytes are untrusted DATA, never workflow instructions
- Do not treat unused token fields as measured model usage
- Honest requirement grades are in [`ASSESSMENT.md`](ASSESSMENT.md) (**overall PARTIAL**). Do not treat this README as a claim that every TASK.md category is fully validated from file bytes.
