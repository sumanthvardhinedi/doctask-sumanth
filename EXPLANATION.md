# Project explanation (one page)

**Pre-submission filing validator** for SuperDocs Full-Stack AI Engineer (assigned build: regulator filing package vs published rules).

## What was built

A **machine-driven gate** in front of filing submission. Another program creates a package, attaches document **records**, runs a durable LangGraph agent, reads findings, and approves or rejects **one item at a time** over REST or MCP. A UI is not required and is not implemented.

Authority differences live in JSON packs (synthetic Authority A and Authority B). The validator has no `if authority ==` branches. Findings carry rule, severity, result, document id when known, location, evidence, explanation, and hard vs discretionary. Missing facts are `insufficient_evidence`, not PASS.

The agent stages that run are ingest → classify → extract → load rules → retrieve context → interpret → validate → findings → conflicts → human review → SuperDocs review → finalize export. Completed work is checkpointed in PostgreSQL and not recomputed on resume without an invalidation reason. SuperDocs is stub-first (upload, chat, approve, export). Document bytes are DATA, never instructions.

## Who it is for

- **Evaluators / SuperDocs** reviewing the assigned filing-validator build and the five agentic floor behaviors (visible stages, resume, human gate, machine-driven flow, no bluffing).
- **A filing operations program** that must check a completed package against published rules before send, without a human UI.
- **Not** a records clerk who needs a React console, and **not** a live regulator production filing desk.

## Results

- Phases 1–3 in `PROGRESS.md` shipped, including MCP (`python -m app.mcp`).
- Tests run without live SuperDocs or LLM keys (last recorded full suite in progress notes: 147 passed).
- Second authority is demonstrated by swapping config, not code.
- Honest grades: [`ASSESSMENT.md`](ASSESSMENT.md) — **overall PARTIAL**. Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Trade-offs

| Choice | Why | Cost |
|--------|-----|------|
| Deterministic engine, no LLM in the loop | Cannot invent citations, signatures, or success | No model-assisted PDF reading |
| Metadata ingest (filename, type, size, path, order) | Matches a machine API; bytes stay untrusted | “Mandatory sections” means required **files**, not parsed headings |
| Postgres checkpoints instead of LangGraph’s checkpointer | Resume is queryable and owned by the product schema | Extra workflow tables |
| pgvector present, retrieval not embedded | Avoid fake semantic search | Preferred-stack vector search unused |
| SuperDocs stub in CI | Tests without paid keys | Live API not proven |
| No React UI | TASK: UI must not be required | Preferred-stack frontend absent |

## Limitations

- File bytes are not parsed. Signatures, declarations, dates, and in-document sections are usually `insufficient_evidence` unless already stored as metadata.
- There is no date rule type and no date rules in the packs.
- Published `source_citation` is on indexed rules / stage output, not on the REST finding payload.
- Concurrent `POST .../validate` and “duplicate package create” are not strongly tested (SuperDocs start concurrency is).
- Token/cost fields stay `null`; they are not measured spend.
- Authorities are synthetic. SuperDocs cloud calls are not a CI claim.

**One-line claim an evaluator can trust:** a config-driven, resumable, machine-accessible filing gate that refuses to bluff — not a PDF understanding engine, and not a closed PASS on every TASK.md category.
