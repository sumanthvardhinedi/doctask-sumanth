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