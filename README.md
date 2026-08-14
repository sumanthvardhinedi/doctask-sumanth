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

Tests run without a live SuperDocs or LLM token. Phase 3A does not call a model, so stage checkpoints store `token_count` / `estimated_cost` as unused (`null`).

```
pip install -r backend/requirements.txt
pytest backend/tests
```

## What exists now

- Create a package and documents over REST
- `POST /api/v1/packages/{id}/validate` starts or resumes the **agent workflow**
- Deterministic validation against indexed Authority A / B rules
- Findings, per-finding approve/reject, SuperDocs review (stub client)

### Agent stages actually executed

`ingest_package` → `load_authority_rules` → `validate_package` → `generate_findings` → `human_review`

Completed stages are checkpointed in Postgres and skipped on resume. Classify, extract, semantic retrieval, interpretation, conflict routing, MCP, and React UI are **not** implemented yet.

### REST (machine interface)

- `POST /api/v1/packages`
- `POST /api/v1/packages/{id}/documents`
- `POST /api/v1/packages/{id}/validate`
- `GET /api/v1/packages/{id}/validation-runs`
- `GET /api/v1/packages/{id}/validation-runs/{run}/findings`
- `POST /api/v1/packages/{id}/validation-runs/{run}/findings/{finding}/approval`
- SuperDocs review/decision/export under `/api/v1/packages/{id}/...`

## Limits

- SuperDocs is stub-first unless a real `SUPERDOCS_API_KEY` is configured locally
- Document bytes are untrusted DATA, never workflow instructions
- Do not treat unused token fields as measured model usage
