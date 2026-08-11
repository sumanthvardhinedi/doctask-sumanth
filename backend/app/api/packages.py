from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    PackageCreateRequest,
    PackageResponse,
)
from app.db.database import get_db
from app.models.filing import FilingPackage, PackageDocument
from app.validator.rules import get_rules_for_authority
from app.workflow.validation_workflow import run_validation
router = APIRouter(
    prefix="/api/v1/packages",
    tags=["packages"],
)


@router.post(
    "",
    response_model=PackageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_package(
    request: PackageCreateRequest,
    db: Session = Depends(get_db),
) -> PackageResponse:
    try:
        get_rules_for_authority(request.authority_code)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    package = FilingPackage(
        authority_code=request.authority_code,
        name=request.name,
    )

    db.add(package)
    db.commit()
    db.refresh(package)

    return PackageResponse(
        id=package.id,
        authority_code=package.authority_code,
        name=package.name,
        status=package.status,
        document_count=0,
    )


@router.post(
    "/{package_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    package_id: UUID,
    request: DocumentCreateRequest,
    db: Session = Depends(get_db),
) -> DocumentResponse:
    package = db.get(FilingPackage, package_id)

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing package not found",
        )

    document = PackageDocument(
        package_id=package.id,
        filename=request.filename,
        content_type=request.content_type,
        file_size_bytes=request.file_size_bytes,
        storage_path=request.storage_path,
        sort_order=request.sort_order,
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return DocumentResponse(
        id=document.id,
        package_id=document.package_id,
        filename=document.filename,
        content_type=document.content_type,
        file_size_bytes=document.file_size_bytes,
        storage_path=document.storage_path,
        sort_order=document.sort_order,
    )


@router.post(
    "/{package_id}/validate",
    status_code=status.HTTP_201_CREATED,
)
def validate_package(
    package_id: UUID,
    db: Session = Depends(get_db),
):
    package = db.get(FilingPackage, package_id)

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing package not found",
        )

    try:
        validation_run = run_validation(db, package_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "id": validation_run.id,
        "package_id": validation_run.package_id,
        "status": validation_run.status,
        "started_at": validation_run.started_at,
        "completed_at": validation_run.completed_at,
    }