Phase 1A–1F
✅ Complete

Phase 2A — Configuration-driven Authority A/B rules
✅ Complete
✅ Committed and pushed

Phase 2B — SuperDocs REST integration
✅ Complete
✅ Four required operations implemented/tested
✅ Committed and pushed

Phase 2C — Filing package REST surface
✅ Package creation
✅ Document ingestion
✅ Package validation
✅ Validation-run retrieval
✅ Validation-findings retrieval
✅ Committed and pushed

Phase 2D Slice 1 — Human finding approval API
✅ Finding approval request/response schemas
✅ Per-finding approval endpoint
✅ Approve / reject finding
✅ Prevent duplicate approval decision
✅ ApprovalDecision persistence
✅ Commit: ff7f4ce feat: add per-finding approval API
✅ Docs: b105349
✅ Full suite at Slice 1: 56 passed, 1 warning

Phase 2D Slice 2 — SuperDocs-assisted review/edit/export
✅ Complete
✅ DocumentStore resolves PackageDocument.storage_path under UPLOADS_ROOT (path-escape safe)
✅ build_edit_instruction from trusted finding metadata; document text wrapped as untrusted DATA
✅ SuperDocsReviewSession persistence (separate from finding ApprovalDecision)
✅ Workflow: start_superdocs_review → decide_superdocs_review → export_superdocs_review
✅ SuperDocs approve() only after human decision; export only after approved status
✅ Rejection path does not export
✅ Findings without package_document_id rejected with explicit 400
✅ REST:
- POST /api/v1/packages/{id}/validation-runs/{run}/findings/{finding}/superdocs-review
- POST /api/v1/packages/{id}/superdocs-reviews/{review}/decision
- POST /api/v1/packages/{id}/superdocs-reviews/{review}/export
✅ Tests: test_superdocs_review.py (8 tests)
✅ Full suite: 64 passed, 1 warning
✅ Assumptions:
- Local uploads root via UPLOADS_ROOT (default uploads/); no S3
- One SuperDocs review session per finding (unique finding_id)
- Finding approval ≠ proposed-change approval

Phase 2E — Resumability, idempotency, concurrency, prompt-injection hardening, observability
✅ Complete
✅ Resumable SuperDocs review workflow with persisted checkpoints
✅ Failed reviews can resume from persisted workflow state
✅ Uploaded and creating checkpoints are handled safely
✅ Concurrent review creation is protected; one request creates the review and the competing request receives 409
✅ Review creation is idempotency-safe for the same finding
✅ SuperDocs approve() remains gated behind explicit human approval
✅ Export remains gated behind APPROVED status
✅ Rejection path does not call SuperDocs approve() or export()
✅ Prompt-injection hardening preserved: document content is explicitly treated as untrusted DATA
✅ Trusted finding metadata remains separated from document content in edit instructions
✅ Structured logging added around review creation, decisions, failures, and workflow stages
✅ Tests: test_superdocs_review.py (11 tests)
✅ Full suite: 67 passed, 1 warning
✅ git diff --check: clean


Phase 2F — Final documentation / second-authority proof / cleanup
✅ Complete
✅ Verified Authority A and Authority B are selected through configuration/data
✅ No authority-specific validation branches introduced
✅ Documented REST package/validation/finding/approval/SuperDocs workflow
✅ Documented SuperDocs resumability, idempotency, concurrency, and prompt-injection protections
✅ Documented machine-driven approval flow; UI is not required
✅ Documented known limitations and stubbed external integrations
✅ Final requirement assessment uses honest PASS / PARTIAL / FAIL statuses
✅ Full test suite passed
✅ git diff --check passed

Phase 3 numbering note (TASK.md agentic plan vs earlier slices)

The slices below labeled 3A indexing / 3B retrieval / 3C indexed-rule wiring were completed before the TASK.md agentic Phase 3 plan was applied. They remain valid work and map to **Phase 3D support** (`load_authority_rules` / deterministic retrieval). Official TASK.md **Phase 3A** is the durable agentic workflow foundation (this next slice). Official 3B/3C are classify_documents / extract_structure and are not those earlier slices.

Phase 3A — Regulatory Rule Persistence & Indexing Foundation

- **Status**: complete
- **Implementation completed**:
  - `IndexedRule` persistence model (`backend/app/models/regulatory_rule.py`)
  - `authority_code` + `rule_id` uniqueness constraint (`uq_indexed_rules_authority_rule`)
  - Idempotent rule indexing (`backend/app/services/rule_indexer.py`)
  - Explicit source citations and keywords required for indexed rules
  - Effective dates and rule metadata persisted without generic fallbacks
  - Authority A & B configuration indexing (`backend/config/authorities/authority_a.json`, `backend/config/authorities/authority_b.json`)
  - Database tables created and verified
- **Important components**:
  - `backend/app/models/regulatory_rule.py`
  - `backend/app/services/rule_indexer.py`
  - `backend/config/authorities/authority_a.json`
  - `backend/config/authorities/authority_b.json`
- **Tests**:
  - `backend/tests/test_rule_indexer.py`
  - Existing Phase 3A indexing coverage
- **Verification**:
  - Authority A indexing: 8 rules
  - Authority B indexing: 7 rules
  - Full backend test suite: 83 passed, 1 warning
  - `git diff --check`: clean
- **Commit**:
  - pending final Phase 3 checkpoint commit
- **Push**:
  - pending
- **Next stage**:
  - Phase 3B — Regulatory Rule Retrieval/Search Engine


Phase 3B — Regulatory Rule Retrieval/Search Engine

- **Status**: complete
- **Implementation completed**:
  - Added deterministic rule retrieval service
  - Retrieval is strictly scoped by `authority_code`
  - Optional category filtering
  - Optional rule-type filtering
  - Metadata/description query matching
  - Deterministic ordering by category and rule ID
  - Configurable result limit
  - Non-positive limits return an empty result
  - Unknown authorities return an empty result
  - Indexed rule metadata is preserved during retrieval
- **Important components**:
  - `backend/app/services/rule_retrieval.py`
  - `backend/tests/test_rule_retrieval.py`
  - `backend/app/services/rule_indexer.py`
- **Tests added**:
  - `backend/tests/test_rule_retrieval.py`
  - 10 retrieval tests covering:
    - Authority A retrieval
    - Authority B retrieval
    - Authority isolation
    - Category filtering
    - Rule-type filtering
    - Rule metadata query matching
    - Result limits
    - Zero/negative limits
    - Unknown authorities
    - Metadata preservation
- **Focused test result**:
  - 10 passed
- **Full backend test result**:
  - 83 passed, 1 warning
- **git diff --check**:
  - clean / no whitespace errors
- **Commit**:
  - pending final commit
- **Push**:
  - pending
- **Next stage**:
  - Official TASK.md Phase 3A — durable agentic workflow foundation


Phase 3C — Validation workflow uses indexed regulatory rules (integration slice)

- **Status**: complete as **Phase 3D supporting work** (not official TASK.md extract_structure)
- **Implementation completed in this slice**:
  - `run_validation` indexes the package authority before loading rules
  - Validation uses persisted `IndexedRule` rows via adapter + provider, not in-memory `get_rules_for_authority()`
  - Empty indexed-rule tables no longer produce a false `COMPLETED` package with zero findings
  - Provider unit tests restore `retrieve_rules` via `patch(...)` so later tests are not polluted
- **Important endpoints/components/workflows**:
  - `backend/app/workflow/validation_workflow.py` (`index_authority_rules` → `get_indexed_rule_definitions` → `validate_package` → persist findings)
  - `backend/app/services/regulatory_rule_adapter.py`
  - `backend/app/services/regulatory_rule_provider.py`
  - `POST /api/v1/packages/{id}/validate`
- **Tests added / used**:
  - `backend/tests/test_regulatory_rule_adapter.py`
  - `backend/tests/test_regulatory_rule_provider.py`
  - Existing `backend/tests/test_workflow.py` and finding-approval API tests (assertions unchanged)
- **Focused test result**:
  - workflow + approval + adapter + provider tests passed
- **Full backend test result**:
  - 90 passed, 1 warning (at slice completion)
- **git diff --check**:
  - clean
- **Commit / push**:
  - included with official Phase 3A commit
- **Remaining next-stage work**:
  - Official TASK.md Phase 3A agent foundation


Phase 3A — Agentic Workflow Foundation (TASK.md)

- **Status**: complete for this slice
- **Implementation completed**:
  - Durable `AgentWorkflow` + `AgentStageCheckpoint` persistence
  - LangGraph `StateGraph` with real stages only: ingest_package → load_authority_rules → validate_package → generate_findings → human_review
  - Legal status transitions; invalid transitions raise `ValueError`
  - Resume skips completed checkpoints and does not create a second validation run
  - `POST /api/v1/packages/{id}/validate` starts or resumes the agent graph
  - Token/cost fields exist on checkpoints and stay unused (`null`) because this slice makes no LLM calls
  - README documents setup, env tokens, and honest limits
- **Important endpoints/components/workflows**:
  - `backend/app/workflow/agent_workflow.py`
  - `backend/app/models/agent_workflow.py`
  - `POST /api/v1/packages/{id}/validate`
  - `README.md`
- **Tests added**:
  - `backend/tests/test_agent_workflow.py` (8 tests): state creation, stage transitions, checkpoint persistence, resume skip, terminal waiting_for_human, invalid transition, missing package, unknown authority
- **Focused test result**:
  - 14 passed (agent + workflow + sample API)
- **Full backend test result**:
  - 98 passed, 1 warning
- **git diff --check**:
  - clean
- **Commit**:
  - `8ebad44` feat: add durable LangGraph agent workflow foundation
- **Push**:
  - `origin/main`
- **Remaining next-stage work**:
  - Official Phase 3B — ingest + classify_documents (no fake classification; evidence-based only)
