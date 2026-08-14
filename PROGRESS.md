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

---

Phase 3 uses the TASK.md agentic plan:

3A agent foundation → 3B classify → 3C extract_structure → 3D rule retrieval/interpretation → …

Rule indexing, retrieval, and validator wiring were built first. They are supporting work for **3D** (`load_authority_rules`), not official 3A–3C.

---

Phase 3 supporting — Regulatory rule indexing

- **Status**: complete
- **Implementation**:
  - `IndexedRule` model and `uq_indexed_rules_authority_rule`
  - Idempotent `index_authority_rules` / `index_all_authorities`
  - Source citations and keywords required
  - Authority A (8 rules) and Authority B (7 rules) JSON configs indexed
- **Components**:
  - `backend/app/models/regulatory_rule.py`
  - `backend/app/services/rule_indexer.py`
  - `backend/config/authorities/authority_a.json`
  - `backend/config/authorities/authority_b.json`
- **Tests**: `backend/tests/test_rule_indexer.py`
- **Suite at the time**: 83 passed, 1 warning
- **Commit**: `17696e1` feat: add phase 3a regulatory rule indexing foundation
- **Push**: origin/main

Phase 3 supporting — Regulatory rule retrieval

- **Status**: complete
- **Implementation**:
  - Deterministic `retrieve_rules()` scoped by `authority_code`
  - Optional category, rule_type, metadata query, limit
  - Unknown authority returns empty (does not invent rules)
- **Components**:
  - `backend/app/services/rule_retrieval.py`
  - `backend/tests/test_rule_retrieval.py`
- **Tests added**: 10 retrieval tests
- **Suite at the time**: 83 passed, 1 warning
- **Commit**: `693bbdc` feat: add regulatory rule retrieval engine
- **Push**: origin/main

Phase 3 supporting — Indexed rules in validation

- **Status**: complete
- **Implementation**:
  - Adapter `IndexedRule` → `RuleDefinition`
  - Provider loads indexed definitions for a configured authority
  - `run_validation` indexes then loads rules (empty index no longer yields a false COMPLETED package)
- **Components**:
  - `backend/app/services/regulatory_rule_adapter.py`
  - `backend/app/services/regulatory_rule_provider.py`
  - `backend/app/workflow/validation_workflow.py`
- **Tests**: `test_regulatory_rule_adapter.py`, `test_regulatory_rule_provider.py`, existing workflow/API tests
- **Commit**: included in `8ebad44`
- **Push**: origin/main

---

Phase 3A — Agentic workflow foundation

- **Status**: complete
- **Implementation**:
  - Durable `AgentWorkflow` + `AgentStageCheckpoint`
  - LangGraph graph with real stages only: ingest_package → load_authority_rules → validate_package → generate_findings → human_review
  - Legal transitions; invalid transitions raise ValueError
  - Resume skips completed checkpoints; does not create a second ValidationRun
  - `POST /api/v1/packages/{id}/validate` starts or resumes the graph
  - Token/cost fields on checkpoints are unused (`null`); no LLM calls in this slice
  - `README.md` added (setup, env tokens, honest limits)
- **Components / endpoints**:
  - `backend/app/workflow/agent_workflow.py`
  - `backend/app/models/agent_workflow.py`
  - `POST /api/v1/packages/{id}/validate`
  - `README.md`
- **Tests added**: `backend/tests/test_agent_workflow.py` (8 tests)
- **Full suite**: 98 passed, 1 warning
- **git diff --check**: clean
- **Commit**: `8ebad44` feat: add durable LangGraph agent workflow foundation
- **Docs**: `5aea0ba` docs: record phase 3A commit hash in PROGRESS.md
- **Push**: origin/main
- **Next**: official Phase 3B — classify_documents (evidence-based only; insufficient evidence must not be fabricated)
