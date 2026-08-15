from enum import StrEnum


class PackageStatus(StrEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FindingResult(StrEnum):
    FAIL = "fail"
    PASS = "pass"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SuperDocsReviewStatus(StrEnum):
    CREATING = "creating"
    UPLOADED = "uploaded"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    FAILED = "failed"


class AgentWorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentWorkflowStage(StrEnum):
    INGEST_PACKAGE = "ingest_package"
    CLASSIFY_DOCUMENTS = "classify_documents"
    EXTRACT_STRUCTURE = "extract_structure"
    LOAD_AUTHORITY_RULES = "load_authority_rules"
    VALIDATE_PACKAGE = "validate_package"
    GENERATE_FINDINGS = "generate_findings"
    HUMAN_REVIEW = "human_review"


class AgentStageCheckpointStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"