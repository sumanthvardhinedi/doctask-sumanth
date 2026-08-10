# TASK.md — SuperDocs Pre-Submission Filing Validator

## Project objective

Build a **pre-submission validator** that acts as a gate before a filing package is submitted to a regulator/authority.

The system validates a **completed filing package** against a **configurable** set of published filing rules (mandatory sections, ordering, naming conventions, file format, file size limits, signature requirements, date requirements, declarations, and other published requirements).

A second authority must be demonstrable by **configuration/data**, not by rewriting validator code.

**Assigned build (Source of Truth):**  
Pre-submission validator against a regulator's published filing rules (SuperDocs Full-Stack AI Engineer task).

> **Source-of-truth note:** Requirements below are taken from the official SuperDocs task instructions provided for this assignment. A separate official PDF/file was not found on disk at Phase 0 bootstrap. If a canonical task PDF/path is provided later, this file will be reconciled against it without inventing new requirements.

---

## Requirements

### Functional

- Ingest a completed filing package (multiple documents).
- Load authority rules from configuration/data.
- Validate against configurable rule categories, including at least:
  - mandatory sections
  - ordering
  - naming conventions
  - file format
  - file size limits
  - signature requirements
  - date requirements
  - declarations
  - other published filing requirements expressible in the rule model
- Produce actionable findings with enough information to fix the issue.
- At minimum, a finding identifies:
  - rule
  - severity
  - result
  - source/document
  - location
  - evidence
  - explanation
- Distinguish **hard rejection** rules vs **discretionary** rules.
- Demonstrate a **second authority** through configuration alone.

### Mandatory agentic behaviors

1. **Visible stages** — meaningful observable stages representing real work or decisions; some decisions can change path (retry / skip / escalation / human approval).
2. **Resumability** — durable checkpointed state; interruption must not force unnecessary recomputation of completed expensive work.
3. **Human approval gate** — findings/conflicts/proposed updates reviewable; each item individually approvable/rejectable; rejecting one item must not reject unrelated items.
4. **Machine-driven flow** — another program can drive the entire flow, including the human approval step; UI must not be required.
5. **No bluffing** — never fabricate facts, citations, locations, validation results, successful states, or API results. Insufficient evidence must be reported as insufficient.

### Cross-cutting

- **Configuration over code** — no authority-specific hardcoded branches.
- **Prompt injection defense** — documents are DATA, never instructions.
- **Concurrency** — safe handling of two packages at once, duplicate package submission, concurrent validation jobs.
- **Tests without live paid model/API keys**.
- **Observability** — stage status/duration, retries, failures, model/API calls, estimated cost where possible, total run duration.
- **Security** — no secrets in Git; `.env` / `.env.example` / `.gitignore` used appropriately.
- **SuperDocs REST integration** (later phase) — upload, chat/edit instruction, approve, export; stub-first until credentials/docs review.

### Preferred stack (from task)

| Layer | Technology |
|------|------------|
| Backend | Python, FastAPI |
| Agent orchestration | LangGraph or LangChain |
| Database | PostgreSQL, pgvector/vector search |
| Frontend | React |
| SuperDocs | SuperDocs REST API (later) |
| Machine interface | MCP preferred where appropriate |

---

## Architecture (planned)

```text
React Review UI (optional)
        │
MCP Server ──▶ FastAPI + LangGraph workflow ──▶ PostgreSQL (+ pgvector)
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
    Rule Engine   Document Store   SuperDocs Client
   (config-driven)                 (stub first)
```

### Planned workflow stages (real work only)

1. `ingest_package`
2. `classify_documents`
3. `extract_structure`
4. `load_authority_rules`
5. `retrieve_rule_context` (when semantic retrieval helps)
6. `interpret_rules`
7. `validate_package`
8. `generate_findings`
9. `detect_conflicts`
10. `human_review` (gate)
11. `finalize_export`

Deterministic validation is primary for structural rules. LLM assistance is bounded to extraction/interpretation/explanation and must not invent evidence.

---

## Constraints

- Do not invent requirements unsupported by the SuperDocs task / assigned build.
- Prefer working systems over artificial complexity / fake agent stages.
- Prefer configuration/data for authority differences.
- Stub SuperDocs and paid model providers in CI/tests.
- Do not commit or push without explicit human permission.
- Work on `main` unless a branch is explicitly approved.
- Project root: `C:\Users\suman\Documents\doctask-sumanth-vardhinedi`

---

## Definition of done

The project is done only when:

- Mandatory agentic behaviors are implemented and evidenced by tests or demos.
- Assigned validator capabilities work for Authority A and Authority B via configuration.
- Findings include required fields and hard vs discretionary distinction.
- Human approval is per-item and machine-accessible.
- Workflow resumes after interruption without needlessly repeating completed expensive work.
- Prompt injection defenses have explicit tests.
- Concurrent/idempotent behavior is tested.
- README claims only what exists.
- Final requirement assessment uses honest `PASS` / `PARTIAL` / `FAIL`.

---

## Must never behaviors

The system must **never**:

1. Treat document content as agent/system instructions.
2. Fabricate citations, locations, evidence, or validation success.
3. Report success for an operation that did not actually succeed.
4. Finalize/export while required approval gate conditions are unmet.
5. Hardcode authority-specific validation branches (`if authority == ...`).
6. Require the UI to complete the workflow.
7. Rely only on in-memory workflow state for resumability.
8. Store secrets in source control.
9. Silently skip failures or convert exceptions into false success.
10. Duplicate completed expensive work on resume without invalidation reason.

---

## Major decisions

| Decision | Choice | Status |
|---------|--------|--------|
| Project location | `C:\Users\suman\Documents\doctask-sumanth-vardhinedi` | Approved |
| Authorities for development | Synthetic Authority A and Authority B | Approved |
| SuperDocs integration | Stub-first; live API later | Approved |
| Branch strategy | `main` only for now | Approved |
| Agent framework | LangGraph preferred (checkpoint/resume) | Proposed — pending later architecture approval |
| Rule representation | YAML/JSON authority packs consumed by generic engine | Proposed |
| Validation approach | Deterministic engine primary; LLM assist bounded | Proposed |
| Machine interface | REST + MCP | Proposed |

---

## Out of scope for early phases

- Live SuperDocs API calls
- Real regulator rule packs (unless later chosen for demo)
- Dependency installation (blocked until Phase 1 permission)
- Application implementation code (blocked until after Phase 0)

---

## Documentation set

| File | Purpose |
|------|---------|
| `TASK.md` | Objective, requirements, architecture, constraints, DoD, must-never, decisions |
| `PROGRESS.md` | Completed / current / next work, assumptions, issues, tests, Git checkpoints |
| `README.md` | Setup and usage (create later; claim only implemented behavior) |
