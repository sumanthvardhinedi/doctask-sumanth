# Final requirement assessment

**Date:** 2026-08-16  
**Scope:** Assigned build — pre-submission filing validator (TASK.md), as implemented on `main`.  
**Grades:** `PASS` = present, evidenced, and honest. `PARTIAL` = real work with a material gap versus the written requirement. `FAIL` = missing or would be a bluff to call done.

This is not a live SuperDocs production filing against a real regulator. Authorities A and B are synthetic JSON packs (an approved project decision).

**Overall: PARTIAL.** The machine-driven agentic validator exists and is tested. It is not a complete reading of every published-rule category from document bytes, it does not use pgvector retrieval, it has no React UI, and it has not been proven against the live SuperDocs API.

---



## Definition of done


| Criterion                                                | Grade       | Evidence / gap                                                                                                                                                                                                                                                                           |
| -------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mandatory agentic behaviors implemented and evidenced    | **PASS**    | Visible stages, Postgres checkpoints, per-item human gate, REST+MCP, insufficient-evidence paths. Tests under `backend/tests/test_agent_*.py`, `test_human_review_gate.py`, `test_mcp.py`.                                                                                               |
| Authority A and B via configuration only                 | **PASS**    | `backend/config/authorities/*.json`. No `if authority ==` in `backend/`. Classifier test uses Authority B config without code branches.                                                                                                                                                  |
| Findings include required fields + hard vs discretionary | **PARTIAL** | REST finding has rule, severity, result, `package_document_id`, location, evidence, explanation, `is_hard_rejection`. Published `source_citation` is on indexed rules / generate_findings checkpoint output, **not** on `FindingResponse`. Package-level findings have null document id. |
| Human approval per-item and machine-accessible           | **PASS**    | REST approval + MCP `decide_finding`. Duplicate decision is 409 / `conflict`. Rejecting one finding does not decide others (`test_mcp.py`, `test_packages_api.py`). SuperDocs decide/export is a second per-item gate.                                                                   |
| Resume without repeating completed expensive work        | **PASS**    | Completed `AgentStageCheckpoint` skipped; SuperDocs resumes CREATING/UPLOADED/FAILED. Not LangGraph’s built-in checkpointer — custom Postgres.                                                                                                                                           |
| Prompt injection defenses have explicit tests            | **PASS**    | Document text wrapped as DATA in SuperDocs instructions (`test_prompt_injection_in_document_does_not_override_instruction`). Classifier/extract ignore instruction-like paths.                                                                                                           |
| Concurrent / idempotent behavior tested                  | **PARTIAL** | SuperDocs concurrent start tested (201/201 or 201/409, one session). Duplicate finding approval 409. Two packages can coexist. **Not** tested: concurrent `POST .../validate` on one package; duplicate package-create rejected as a duplicate.                                          |
| README claims only what exists                           | **PASS**    | README states React is not implemented, SuperDocs stub-first, tokens unused unless recorded.                                                                                                                                                                                             |
| This assessment uses PASS / PARTIAL / FAIL               | **PASS**    | This file.                                                                                                                                                                                                                                                                               |


The project is **not** “done” under TASK.md’s “only when” list, because findings’ source field and concurrency coverage are incomplete.

---



## Functional requirements


| Requirement                                                | Grade       | Notes                                                                                                                                                                                               |
| ---------------------------------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ingest a completed filing package (multiple documents)     | **PARTIAL** | REST/MCP accept multiple document **records** (filename, type, size, storage_path, order). Package create does not upload bytes. SuperDocs reads bytes only from `UPLOADS_ROOT` + `storage_path`.   |
| Load authority rules from configuration/data               | **PASS**    | JSON packs → indexer → generic engine.                                                                                                                                                              |
| Mandatory sections                                         | **PARTIAL** | Encoded as `required_document` **filenames**, not parsed sections inside a PDF. Extract marks `sections` as `insufficient_evidence` because bytes are not parsed.                                   |
| Ordering                                                   | **PASS**    | `document_order` vs `sort_order` filenames.                                                                                                                                                         |
| Naming conventions                                         | **PASS**    | `filename_pattern`.                                                                                                                                                                                 |
| File format                                                | **PASS**    | `allowed_content_types` vs declared `content_type` (not magic-byte sniffing).                                                                                                                       |
| File size limits                                           | **PASS**    | `max_file_size` vs declared `file_size_bytes`. Unknown size → `insufficient_evidence`.                                                                                                              |
| Signature requirements                                     | **PARTIAL** | Evaluator exists (`requires_signature`). Extract does **not** read file bytes, so agent runs typically yield `insufficient_evidence` unless metadata already has an observed boolean.               |
| Date requirements                                          | **PARTIAL** | Extract records dates as unobserved. **No** date rule type in the engine. **No** date rules in Authority A/B packs. An unknown `rule_type` would be `insufficient_evidence`, not a fabricated pass. |
| Declarations                                               | **PARTIAL** | Same pattern as signatures. Authority A has a discretionary (`is_hard_rejection: false`) declaration rule. Agent path usually insufficient evidence.                                                |
| Other published requirements expressible in the rule model | **PASS**    | Unsupported `rule_type` → `insufficient_evidence` with an explicit reason.                                                                                                                          |
| Actionable findings                                        | **PASS**    | Explanation + evidence + location are stored. Quality is as good as metadata rules allow.                                                                                                           |
| Hard vs discretionary                                      | **PASS**    | `is_hard_rejection` on rules and findings. Authority A declaration is discretionary.                                                                                                                |
| Second authority by config alone                           | **PASS**    | Authority B: different filenames, prefixes, 5 MB cap, signature on executive summary, no declaration rule.                                                                                          |


---



## Mandatory agentic behaviors


| Behavior               | Grade    | Notes                                                                                                                                                                                                                                                                                                                                   |
| ---------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Visible stages      | **PASS** | Real stages only (ingest → classify → extract → load rules → retrieve → interpret → validate → findings → conflicts → human_review → superdocs_review → finalize_export). Path changes: wait for human, skip SuperDocs for rejected/unreadable items, fail the workflow on errors. `GET .../agent-workflow` / MCP `get_agent_workflow`. |
| 2. Resumability        | **PASS** | Durable `agent_workflows` / `agent_stage_checkpoints`. Resume does not create a second `ValidationRun`.                                                                                                                                                                                                                                 |
| 3. Human approval gate | **PASS** | Findings, conflict-mapped PASS findings, and SuperDocs proposed changes are per-item. “Proposed updates” in this build means SuperDocs proposed edits, not a generic document-pile update register.                                                                                                                                     |
| 4. Machine-driven flow | **PASS** | REST + MCP stdio (`python -m app.mcp`). UI not required. React is absent (preferred stack only).                                                                                                                                                                                                                                        |
| 5. No bluffing         | **PASS** | Unknown files / missing signatures / missing descriptions → `insufficient_evidence`. Token/cost stay `null`. MCP errors return `ok: false`. SuperDocs export is not reported if it did not run.                                                                                                                                         |


---



## Cross-cutting


| Requirement                  | Grade       | Notes                                                                                                                                                                                                                    |
| ---------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Configuration over code      | **PASS**    | No authority-specific validator branches found.                                                                                                                                                                          |
| Prompt injection defense     | **PASS**    | Documents are DATA in SuperDocs chat; tests exist. Not a full adversarial red-team.                                                                                                                                      |
| Concurrency                  | **PARTIAL** | See DoD row above.                                                                                                                                                                                                       |
| Tests without live paid keys | **PASS**    | Suite uses mocks/stubs. Latest recorded full suite: 147 passed.                                                                                                                                                          |
| Observability                | **PASS**    | Stage status, duration, retries, failures, elapsed vs total (total only when completed/failed). SuperDocs API ops counted from persisted sessions only. **Estimated cost is never computed** (no pricing, no LLM usage). |
| Security (no secrets in Git) | **PASS**    | `.env` gitignored; `.env.example` has placeholders and a **local docker** DB password, labeled not for production.                                                                                                       |
| SuperDocs REST (stub-first)  | **PASS**    | Client: upload, chat, approve, export. Workflow: start → human decide → approve only if approved → export. Live API against SuperDocs is **not** claimed.                                                                |


---



## Preferred stack


| Layer                 | Grade       | Notes                                                                                                                                                      |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python / FastAPI      | **PASS**    |                                                                                                                                                            |
| LangGraph             | **PASS**    | Graph orchestration. Checkpoint/resume is our Postgres model, not LangGraph persistence.                                                                   |
| PostgreSQL + pgvector | **PARTIAL** | Postgres is used. `pgvector` extension and an unused `IndexedRule.embedding` column exist. Retrieval is deterministic metadata lookup — **no embeddings**. |
| React                 | **FAIL**    | No frontend. TASK architecture marks UI optional; machine flow does not need it.                                                                           |
| SuperDocs REST        | **PARTIAL** | Stub-first client and agent loop exist; live credentials/docs review not done.                                                                             |
| MCP                   | **PASS**    | Stdio server wrapping the same operations.                                                                                                                 |


---



## Must-never behaviors


| #   | Rule                                              | Grade                                                    |
| --- | ------------------------------------------------- | -------------------------------------------------------- |
| 1   | Document content is not agent/system instructions | **PASS**                                                 |
| 2   | No fabricated citations / evidence / success      | **PASS** (within metadata-only extract)                  |
| 3   | No success for operations that did not succeed    | **PASS**                                                 |
| 4   | No finalize/export if gates unmet                 | **PASS**                                                 |
| 5   | No `if authority ==` validation                   | **PASS**                                                 |
| 6   | UI not required                                   | **PASS**                                                 |
| 7   | Resumability not in-memory-only                   | **PASS**                                                 |
| 8   | No secrets in source control                      | **PASS** (local docker password in example/compose only) |
| 9   | Failures not converted to false success           | **PASS**                                                 |
| 10  | No silent re-do of completed expensive work       | **PASS**                                                 |


---



## What a reviewer should not believe

- That PDFs were parsed for signatures, declarations, dates, or sections.
- That `token_count` / `estimated_cost` measure model spend.
- That pgvector search is in use.
- That SuperDocs live cloud calls were verified in CI.
- That a React review UI exists.
- That this is a real regulator’s published instrument (packs are synthetic).

---



## Remaining work (if the assigned build is to be closed as PASS)

1. Persist and return finding **source** (`source_citation`) on the REST/MCP finding payload.
2. Either parse document bytes for signature/declaration/date/section rules **without inventing**, or keep those categories `insufficient_evidence` and say so in every demo.
3. Add a date rule type **or** drop “date requirements” from the demo script until a pack contains a real date rule.
4. Tests for concurrent validation of two packages / same package.
5. Live SuperDocs against documented credentials (still stub in CI).
6. React UI only if a human review surface is wanted; not required for DoD machine flow.
7. Semantic retrieval only if it improves rule context; do not add embeddings for appearance.

**Recommended demo claim:** “Metadata-and-config filing gate with a durable agent, per-item human/SuperDocs decisions, REST+MCP, and honest insufficient evidence — not a PDF understanding engine.”