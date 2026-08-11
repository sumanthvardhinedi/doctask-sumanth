from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    FindingResponse,
    PackageCreateRequest,
    PackageResponse,
    ValidationRunResponse,
)
from app.db.database import get_db
from app.models.finding import Finding
from app.models.filing import FilingPackage, PackageDocument
from app.models.validation import ValidationRun
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


@router.get(
    "/{package_id}/validation-runs",
    response_model=list[ValidationRunResponse],
)
def get_validation_runs(
    package_id: UUID,
    db: Session = Depends(get_db),
) -> list[ValidationRunResponse]:
    package = db.get(FilingPackage, package_id)

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing package not found",
        )

    runs = db.scalars(
        select(ValidationRun)
        .where(ValidationRun.package_id == package_id)
        .order_by(ValidationRun.created_at.desc())
    ).all()

    return [
        ValidationRunResponse(
            id=run.id,
            package_id=run.package_id,
            authority_code=run.authority_code,
            status=run.status,
            current_stage=run.current_stage,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )
        for run in runs
    ]


@router.get(
    "/{package_id}/validation-runs/{validation_run_id}/findings",
    response_model=list[FindingResponse],
)
def get_validation_findings(
    package_id: UUID,
    validation_run_id: UUID,
    db: Session = Depends(get_db),
) -> list[FindingResponse]:
    package = db.get(FilingPackage, package_id)

    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Filing package not found",
        )

    validation_run = db.get(ValidationRun, validation_run_id)

    if validation_run is None or validation_run.package_id != package_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Validation run not found",
        )

    findings = db.scalars(
        select(Finding)
        .where(Finding.validation_run_id == validation_run_id)
        .order_by(Finding.created_at.asc())
    ).all()

    return [
        FindingResponse(
            id=finding.id,
            validation_run_id=finding.validation_run_id,
            package_document_id=finding.package_document_id,
            rule_id=finding.rule_id,
            rule_category=finding.rule_category,
            severity=finding.severity,
            result=finding.result,
            location=finding.location,
            evidence=finding.evidence,
            explanation=finding.explanation,
            is_hard_rejection=finding.is_hard_rejection,
        )
        for finding in findings
    ]