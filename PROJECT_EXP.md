# SuperDocs Pre-Submission Regulatory Filing Validator

## 1. Project Overview

This project is a pre-submission filing validator for SuperDocs.

The idea is simple: before a filing package is submitted, the system checks the package against the applicable regulatory rules and produces findings that can be reviewed and acted on.

The system is designed as a machine-driven workflow rather than a UI-first application. Another program or machine client can create a filing package, attach document records, start validation, inspect findings, approve or reject items, and continue the workflow through REST APIs or the application's MCP interface.

The main goal was not to build a PDF editor or a general-purpose chatbot. The goal was to build a reliable validation gate that can say:

- PASS when the available evidence supports the requirement.
- FAIL when the available evidence contradicts the requirement.
- `insufficient_evidence` when the system does not have enough information to make a trustworthy decision.

The last case is particularly important. The system should not invent a fact simply to produce a PASS.

---



## 2. What I Built

The implementation contains the following major pieces:

- FastAPI REST API
- PostgreSQL persistence
- pgvector extension support
- LangGraph-based workflow orchestration
- Configuration-driven regulatory rules
- Rule indexing and retrieval
- Deterministic validation engine
- Findings and approval workflow
- Human approval gate
- Resumable workflow checkpoints
- SuperDocs REST client
- Our own MCP server
- Automated tests

The implementation is organized around a filing package rather than individual isolated documents.

A package can contain multiple document records, and the validator evaluates the package against the rules belonging to the selected authority.

---



## 3. High-Level Flow

The main workflow is:

```text
Filing Package
      |
      v
Document Ingest
      |
      v
Classification
      |
      v
Structure / Extraction
      |
      v
Load Regulatory Rules
      |
      v
Retrieve Rule Context
      |
      v
Interpret Rules
      |
      v
Validate
      |
      v
Generate Findings
      |
      v
Conflict Detection
      |
      v
Human Review
      |
      v
SuperDocs Review
      |
      v
Finalize / Export
```

