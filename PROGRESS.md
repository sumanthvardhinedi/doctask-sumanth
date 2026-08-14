# Progress

All listed phases below are complete and on `origin/main` unless marked otherwise.

## Phase 1 — Project and validator foundation

| Slice | What shipped | Commit |
|------|----------------|--------|
| 1A | `TASK.md` / project documentation | `021fb07` |
| 1B | FastAPI app and health endpoint | `a524bb6` |
| 1C | PostgreSQL + pgvector database foundation | `12026dc` |
| 1D | Regulatory domain models | `c56515e` |
| 1E | Deterministic validator | `ffd0346` |
| 1F | Validation workflow foundation | `7b9799a`, docs `d0cd0b4` |

## Phase 2 — Reliable backend, approval, SuperDocs

### 2A — Configuration-driven Authority A/B

- Authority rules live in JSON config, not `if authority == …` branches
- Commit: `94fc3a0` feat: externalize regulatory authority rules
- Docs: `02ebbba`

### 2B — SuperDocs REST (stub-first)

- Four operations: upload, chat, approve, export
- Commit: `207cb28` Implement SuperDocs REST integration

### 2C — Filing package REST

- Package create, document ingest, validate, list runs, list findings
- Commits: `bd37435`, `3385faf`, `9f55fe2`, `928d9ec`

### 2D — Human approval and SuperDocs review

**Slice 1 — per-finding approval**

- Approve / reject one finding; duplicate decision returns 409
- `ApprovalDecision` persistence
- Commit: `ff7f4ce` feat: add per-finding approval API
- Docs: `b105349`
- Suite at the time: 56 passed, 1 warning

**Slice 2 — SuperDocs-assisted review**

- Path-safe `DocumentStore`; edit instruction from trusted finding metadata; document text is untrusted DATA
- `SuperDocsReviewSession` is separate from finding approval
- Flow: start → human decision → SuperDocs approve only if approved → export; reject does not export
- Findings without `package_document_id` return 400
- REST: `.../findings/{finding}/superdocs-review`, `.../superdocs-reviews/{review}/decision`, `.../export`
- Assumptions: local `UPLOADS_ROOT`; one SuperDocs session per finding
- Commit: `0ce2fc7` feat: add SuperDocs-assisted review workflow
- Suite at the time: 64 passed, 1 warning

### 2E — Resume, concurrency, prompt injection, observability

- SuperDocs checkpoints resume (creating / uploaded / failed)
- Concurrent create: one winner, other 409; same finding is idempotent
- Approve/export still gated; document content never becomes instructions
- Structured logging around review stages
- Tests: `test_superdocs_review.py` (11 tests)
- Commit: `4dbb091` feat: complete phase 2e superdocs reliability
- Suite at the time: 67 passed, 1 warning

### 2F — Assessment and cleanup

- Authority A/B via configuration only; machine-driven flow (UI not required)
- Honest PASS / PARTIAL / FAIL in the final assessment
- Commit: `76f8eb0` docs: complete phase 2f final assessment

## Phase 3 — Agentic workflow (TASK.md order)

Official order: **3A** agent foundation → **3B** classify → **3C** extract_structure → **3D** rule retrieval/interpretation → …

Indexing, retrieval, and validator wiring were built first. They support **3D** (`load_authority_rules`), not official 3A–3C.

### Supporting — Rule indexing

- `IndexedRule` + unique `(authority_code, rule_id)`
- Idempotent indexer; citations and keywords required
- Authority A: 8 rules; Authority B: 7 rules
- Tests: `backend/tests/test_rule_indexer.py`
- Suite at the time: 83 passed, 1 warning
- Commit: `17696e1` feat: add phase 3a regulatory rule indexing foundation

### Supporting — Rule retrieval

- `retrieve_rules()` scoped by authority; optional category, type, query, limit
- Unknown authority returns empty (does not invent rules)
- Tests: `backend/tests/test_rule_retrieval.py` (10 tests)
- Suite at the time: 83 passed, 1 warning
- Commit: `693bbdc` feat: add regulatory rule retrieval engine

### Supporting — Indexed rules in validation

- Adapter `IndexedRule` → `RuleDefinition`; provider loads indexed definitions
- `run_validation` indexes then loads rules (empty index no longer yields a false COMPLETED package)
- Tests: `test_regulatory_rule_adapter.py`, `test_regulatory_rule_provider.py`
- Commit: included in `8ebad44`

### 3A — Agentic workflow foundation

- Durable `AgentWorkflow` + `AgentStageCheckpoint`
- LangGraph stages that already do real work: ingest_package → load_authority_rules → validate_package → generate_findings → human_review
- Invalid transitions raise `ValueError`; resume skips completed checkpoints (no second `ValidationRun`)
- `POST /api/v1/packages/{id}/validate` starts or resumes the graph
- Token/cost checkpoint fields exist and stay `null` (no LLM calls in this slice)
- `README.md`: setup, env tokens, honest limits
- Tests: `backend/tests/test_agent_workflow.py` (8 tests)
- Full suite: 98 passed, 1 warning
- Commit: `8ebad44` feat: add durable LangGraph agent workflow foundation
- Docs: `5aea0ba`, `cf76750`
- **Next**: official 3B — `classify_documents` (evidence-based only; do not fabricate labels)
