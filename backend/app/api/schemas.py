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