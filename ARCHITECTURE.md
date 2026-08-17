
# Architecture (one page)

Pre-submission filing validator as implemented. A UI is not in this system. Machines drive the flow over REST or MCP.

## System

```mermaid
flowchart LR
  subgraph machines [Machine clients]
    REST[REST client]
    MCP[MCP stdio server]
  end

  subgraph api [FastAPI]
    PKG[Package and findings APIs]
    OBS[Agent observability]
    LG[LangGraph agent]
  end

  subgraph data [Persistence]
    PG[(PostgreSQL)]
    VEC[pgvector installed\nembeddings unused]
    FS[Local document store]
    CFG[Authority JSON packs]
  end

  subgraph side [Side systems]
    RULE[Deterministic rule engine]
    SD[SuperDocs client\nstub-first]
  end

  REST --> PKG
  MCP --> PKG
  PKG --> LG
  OBS --> PG
  LG --> PG
  LG --> RULE
  RULE --> CFG
  LG --> FS
  LG --> SD
  PKG --> PG
  PG --- VEC
```

## Agent stages that actually run

Completed stages are checkpointed in Postgres and skipped on resume. `human_review` and SuperDocs wait per item. Export does not run if those gates are unmet.

```mermaid
flowchart TD
  A[ingest_package] --> B[classify_documents]
  B --> C[extract_structure]
  C --> D[load_authority_rules]
  D --> E[retrieve_rule_context]
  E --> F[interpret_rules]
  F --> G[validate_package]
  G --> H[generate_findings]
  H --> I[detect_conflicts]
  I --> J[human_review]
  J -->|waiting: missing decisions| J
  J -->|gate met| K[superdocs_review]
  K -->|waiting: SuperDocs decisions| K
  K -->|loop ready| L[finalize_export]
```

## Honest boundaries

| Piece | What it is | What it is not |
|-------|------------|----------------|
| Classification / extract | Filename and stored metadata | PDF/section/signature/date parsing |
| Rule retrieval | Deterministic indexed lookup | Vector/semantic search |
| Validation | Config-driven engine | Authority `if` branches or invented PASS |
| SuperDocs | upload / chat / approve / export, stub in tests | Proven live production API |
| Observability | Stage status, duration, retries, failures | Measured LLM token cost |
| Frontend | None | React review UI |

Rendered visuals for evaluators:

- One-pager poster: [`docs/architecture.png`](docs/architecture.png)
- Exact Mermaid renders: [`docs/architecture-system.png`](docs/architecture-system.png), [`docs/architecture-stages.png`](docs/architecture-stages.png)
