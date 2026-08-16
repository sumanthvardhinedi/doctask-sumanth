from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PackageCreateRequest(BaseModel):
    authority_code: str
    name: str


class PackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    authority_code: str
    name: str
    status: str
    document_count: int


class DocumentCreateRequest(BaseModel):
    filename: str
    content_type: str
    file_size_bytes: int
    storage_path: str
    sort_order: int


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    package_id: UUID
    filename: str
    content_type: str
    file_size_bytes: int
    storage_path: str
    sort_order: int


class PackageDetailResponse(PackageResponse):
    documents: list[DocumentResponse]


class ValidationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    package_id: UUID
    authority_code: str
    status: str
    current_stage: str | None
    started_at: datetime | None
    completed_at: datetime | None


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    validation_run_id: UUID
    package_document_id: UUID | None
    rule_id: str
    rule_category: str
    severity: str
    result: str
    location: str | None
    evidence: str | None
    explanation: str
    is_hard_rejection: bool
    approved: bool | None = None
    reviewer_notes: str | None = None


class FindingApprovalRequest(BaseModel):
    approved: bool
    reviewer_notes: str | None = None


class FindingApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    finding_id: UUID
    approved: bool
    reviewer_notes: str | None
    decided_at: datetime


class SuperDocsReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    package_id: UUID
    validation_run_id: UUID
    finding_id: UUID
    package_document_id: UUID
    status: str
    current_stage: str | None
    edit_instruction: str
    superdocs_session_id: str
    job_id: str
    proposed_changes: dict | list
    export_result: dict | list | None = None
    human_approved: bool | None = None
    human_notes: str | None = None
    decided_at: datetime | None = None


class SuperDocsReviewDecisionRequest(BaseModel):
    approved: bool
    human_notes: str | None = None


class AgentApiOperation(BaseModel):
    provider: str
    operation: str
    count: int


class AgentStageObservability(BaseModel):
    stage: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    elapsed_ms: int | None
    error: str | None
    model_provider: str | None
    model_operation: str | None
    token_count: int | None
    estimated_cost: float | None


class AgentWorkflowObservability(BaseModel):
    id: UUID
    package_id: UUID
    validation_run_id: UUID | None
    status: str
    current_stage: str | None
    retry_count: int
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None
    elapsed_ms: int | None
    total_duration_ms: int | None
    failed_stage_count: int
    waiting_stage_count: int
    completed_stage_count: int
    skipped_stage_count: int
    token_count: int | None
    estimated_cost: float | None
    api_operations: list[AgentApiOperation]
    stages: list[AgentStageObservability]
