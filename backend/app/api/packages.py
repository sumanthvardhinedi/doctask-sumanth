from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_document_store, get_superdocs_client
from app.api.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    FindingApprovalRequest,
    FindingApprovalResponse,
    FindingResponse,
    PackageCreateRequest,
    PackageResponse,
    SuperDocsReviewDecisionRequest,
    SuperDocsReviewResponse,
    ValidationRunResponse,
)
from app.db.database import get_db
from app.integrations.superdocs.client import SuperDocsClient
from app.models.filing import FilingPackage, PackageDocument
from app.models.finding import ApprovalDecision, Finding
from app.models.validation import ValidationRun
from app.storage.document_store import DocumentStore
from app.validator.rules import get_rules_for_authority
# from app.workflow.superdocs_review import (
#     SuperDocsReviewError,
#     decide_superdocs_review,
#     export_superdocs_review,
#     start_superdocs_review,
# )
from app.workflow.superdocs_review import (
    SuperDocsReviewAlreadyExists,
    SuperDocsReviewError,
    decide_superdocs_review,
    export_superdocs_review,
    start_superdocs_review,
)
from app.workflow.validation_workflow import run_validation


router = APIRouter(
    prefix="/api/v1/packages",
    tags=["packages"],
)


def _review_response(review) -> SuperDocsReviewResponse:
    export_result = None
    if review.export_result_json:
        export_result = json.loads(review.export_result_json)

    proposed_changes: dict | list = {}
    if review.proposed_changes_json:
        proposed_changes = json.loads(review.proposed_changes_json)

    return SuperDocsReviewResponse(
        id=review.id,
        package_id=review.package_id,
        validation_run_id=review.validation_run_id,
        finding_id=review.finding_id,
        package_document_id=review.package_document_id,
        status=review.status,
        current_stage=review.current_stage,
        edit_instruction=review.edit_instruction,
        superdocs_session_id=review.superdocs_session_id,
        job_id=review.job_id,
        proposed_changes=proposed_changes,
        export_result=export_result,
        human_approved=review.human_approved,
        human_notes=review.human_notes,
        decided_at=review.decided_at,
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


@router.post(
    "/{package_id}/validation-runs/{validation_run_id}/findings/{finding_id}/approval",
    response_model=FindingApprovalResponse,
)
def approve_finding(
    package_id: UUID,
    validation_run_id: UUID,
    finding_id: UUID,
    request: FindingApprovalRequest,
    db: Session = Depends(get_db),
) -> FindingApprovalResponse:
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

    finding = db.get(Finding, finding_id)

    if finding is None or finding.validation_run_id != validation_run_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finding not found",
        )

    if finding.approval_decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finding already has an approval decision",
        )

    decision = ApprovalDecision(
        finding_id=finding.id,
        approved=request.approved,
        reviewer_notes=request.reviewer_notes,
    )

    db.add(decision)
    db.commit()
    db.refresh(decision)

    return FindingApprovalResponse(
        id=decision.id,
        finding_id=decision.finding_id,
        approved=decision.approved,
        reviewer_notes=decision.reviewer_notes,
        decided_at=decision.decided_at,
    )


@router.post(
    "/{package_id}/validation-runs/{validation_run_id}/findings/{finding_id}/superdocs-review",
    response_model=SuperDocsReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{package_id}/validation-runs/{validation_run_id}/findings/{finding_id}/superdocs-review",
    response_model=SuperDocsReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/{package_id}/validation-runs/{validation_run_id}/findings/{finding_id}/superdocs-review",
    response_model=SuperDocsReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_superdocs_review(
    package_id: UUID,
    validation_run_id: UUID,
    finding_id: UUID,
    db: Session = Depends(get_db),
    client: SuperDocsClient = Depends(get_superdocs_client),
    document_store: DocumentStore = Depends(get_document_store),
) -> SuperDocsReviewResponse:
    try:
        review = start_superdocs_review(
            db,
            package_id=package_id,
            validation_run_id=validation_run_id,
            finding_id=finding_id,
            client=client,
            document_store=document_store,
        )

    except SuperDocsReviewAlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except SuperDocsReviewError as exc:
        detail = str(exc)

        status_code = status.HTTP_400_BAD_REQUEST

        if "not found" in detail.lower():
            status_code = status.HTTP_404_NOT_FOUND

        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    return _review_response(review)


@router.post(
    "/{package_id}/superdocs-reviews/{review_id}/decision",
    response_model=SuperDocsReviewResponse,
)
def decide_superdocs_review_endpoint(
    package_id: UUID,
    review_id: UUID,
    request: SuperDocsReviewDecisionRequest,
    db: Session = Depends(get_db),
    client: SuperDocsClient = Depends(get_superdocs_client),
) -> SuperDocsReviewResponse:
    try:
        review = decide_superdocs_review(
            db,
            package_id=package_id,
            review_id=review_id,
            approved=request.approved,
            human_notes=request.human_notes,
            client=client,
        )

    except SuperDocsReviewError as exc:
        detail = str(exc)

        status_code = status.HTTP_400_BAD_REQUEST

        if "not found" in detail.lower():
            status_code = status.HTTP_404_NOT_FOUND
        elif "already has a human decision" in detail.lower():
            status_code = status.HTTP_409_CONFLICT

        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    return _review_response(review)


@router.post(
    "/{package_id}/superdocs-reviews/{review_id}/export",
    response_model=SuperDocsReviewResponse,
)
def export_superdocs_review_endpoint(
    package_id: UUID,
    review_id: UUID,
    db: Session = Depends(get_db),
    client: SuperDocsClient = Depends(get_superdocs_client),
) -> SuperDocsReviewResponse:
    try:
        review = export_superdocs_review(
            db,
            package_id=package_id,
            review_id=review_id,
            client=client,
        )

    except SuperDocsReviewError as exc:
        detail = str(exc)

        status_code = status.HTTP_400_BAD_REQUEST

        if "not found" in detail.lower():
            status_code = status.HTTP_404_NOT_FOUND

        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    return _review_response(review)
def decide_superdocs_review_endpoint(
    package_id: UUID,
    review_id: UUID,
    request: SuperDocsReviewDecisionRequest,
    db: Session = Depends(get_db),
    client: SuperDocsClient = Depends(get_superdocs_client),
) -> SuperDocsReviewResponse:
    try:
        review = decide_superdocs_review(
            db,
            package_id=package_id,
            review_id=review_id,
            approved=request.approved,
            human_notes=request.human_notes,
            client=client,
        )
    except SuperDocsReviewError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail.lower():
            status_code = status.HTTP_404_NOT_FOUND
        elif "already has a human decision" in detail.lower():
            status_code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return _review_response(review)


@router.post(
    "/{package_id}/superdocs-reviews/{review_id}/export",
    response_model=SuperDocsReviewResponse,
)
def export_superdocs_review_endpoint(
    package_id: UUID,
    review_id: UUID,
    db: Session = Depends(get_db),
    client: SuperDocsClient = Depends(get_superdocs_client),
) -> SuperDocsReviewResponse:
    try:
        review = export_superdocs_review(
            db,
            package_id=package_id,
            review_id=review_id,
            client=client,
        )
    except SuperDocsReviewError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in detail.lower():
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return _review_response(review)
