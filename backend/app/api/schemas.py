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