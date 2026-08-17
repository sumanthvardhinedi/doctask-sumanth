# Project explanation

**Pre-submission filing validator** — SuperDocs Full-Stack AI Engineer assigned build: check a completed filing package against published authority rules before submission.

---

## What was built

A **machine-driven gate** in front of filing submission. Another program can:

1. Create a package and attach document **records**
2. Run a durable LangGraph agent
3. Read findings
4. Approve or reject **one item at a time** over REST or MCP

A UI is not required and is not implemented.

**Rules and findings.** Authority differences live in JSON packs (synthetic Authority A and Authority B). The validator has no `if authority == …` branches. Each finding carries rule, severity, result, document id when known, location, evidence, explanation, and hard vs discretionary. Missing facts are reported as `insufficient_evidence`, never as PASS.

**Agent path.** Stages that actually run:

`ingest` → `classify` → `extract` → `load rules` → `retrieve context` → `interpret` → `validate` → `findings` → `conflicts` → `human review` → `SuperDocs review` → `finalize export`

Completed work is checkpointed in PostgreSQL and is not recomputed on resume without an invalidation reason. SuperDocs is stub-first (upload, chat, approve, export). Document bytes are treated as DATA, never as instructions.

---

## Who it is for

| Audience | Fit |
|----------|-----|
| Evaluators / SuperDocs | Reviewing the assigned build and the five agentic floor behaviors: visible stages, resume, human gate, machine-driven flow, no bluffing |
| Filing operations programs | Checking a completed package against published rules before send, without a human UI |
| Not for | A records clerk who needs a React console, or a live regulator production filing desk |

---

## Results

- Phases 1–3 in [`PROGRESS.md`](PROGRESS.md) shipped, including MCP (`python -m app.mcp` from `backend/`)
- Tests run without live SuperDocs or LLM keys (last recorded full suite: **147 passed**)
- A second authority is demonstrated by swapping configuration, not code
- Honest grades: [`ASSESSMENT.md`](ASSESSMENT.md) — **overall PARTIAL**
- Architecture one-pager: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## Trade-offs

| Choice | Why | Cost |
|--------|-----|------|
| Deterministic engine; no LLM in the loop | Cannot invent citations, signatures, or success | No model-assisted PDF reading |
| Metadata ingest (filename, type, size, path, order) | Fits a machine API; bytes stay untrusted | “Mandatory sections” means required **files**, not parsed headings |
| Postgres checkpoints (not LangGraph’s checkpointer) | Resume is queryable and owned by the product schema | Extra workflow tables |
| pgvector installed; retrieval not embedded | Avoids fake semantic search | Preferred-stack vector search unused |
| SuperDocs stub in CI | Tests without paid keys | Live API not proven |
| No React UI | TASK: UI must not be required | Preferred-stack frontend absent |

---

## Limitations

- File bytes are not parsed. Signatures, declarations, dates, and in-document sections are usually `insufficient_evidence` unless already stored as metadata.
- There is no date rule type and no date rules in the packs.
- Published `source_citation` lives on indexed rules / stage output, not on the REST finding payload.
- Concurrent `POST …/validate` and duplicate package-create are not strongly tested (SuperDocs start concurrency is).
- Token and cost fields stay `null`; they are not measured spend.
- Authorities are synthetic. SuperDocs cloud calls are not a CI claim.

---

## Evaluator claim

A config-driven, resumable, machine-accessible filing gate that refuses to bluff — not a PDF-understanding engine, and not a closed PASS on every TASK.md category.
