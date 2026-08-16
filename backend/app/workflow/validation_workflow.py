import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import FindingResult, PackageStatus, ValidationRunStatus
from app.models.filing import FilingPackage
from app.models.validation import ValidationRun
from app.services.regulatory_rule_provider import get_indexed_rule_definitions
from app.services.rule_indexer import index_authority_rules
from app.validator.engine import validate_package
from app.validator.persistence import map_findings_to_models
from app.validator.types import DocumentInput, PackageInput


def _observed_bool(field: object) -> bool | None:
    """Only a boolean observed on extracted structure counts. Missing evidence is None."""

    if not isinstance(field, dict):
        return None
    if field.get("result") != "observed":
        return None
    value = field.get("value")
    if isinstance(value, bool):
        return value
    return None


def package_input_from_extracted_structure(
    package: FilingPackage,
    extracted_structure: dict[str, object],
) -> PackageInput:
    """Build validator input from extract_structure evidence. Never invent PASS facts."""

    extracted_documents = list(extracted_structure.get("documents") or [])
    documents = tuple(
        DocumentInput(
            filename=str(item.get("filename") or ""),
            content_type=str(item.get("content_type") or ""),
            file_size_bytes=(
                int(item["file_size_bytes"])
                if item.get("file_size_bytes") is not None
                else None
            ),
            sort_order=int(item.get("sort_order") or 0),
            has_signature=_observed_bool(item.get("signature")),
            declaration_present=_observed_bool(item.get("declaration")),
        )
        for item in extracted_documents
    )

    return PackageInput(
        authority_code=package.authority_code,
        name=package.name,
        documents=documents,
    )


def _build_package_input(package: FilingPackage) -> PackageInput:
    """Convert persisted package data into pure validator input."""
    documents = tuple(
        DocumentInput(
            filename=document.filename,
            content_type=document.content_type,
            file_size_bytes=document.file_size_bytes,
            sort_order=document.sort_order,
        )
        for document in sorted(
            package.documents,
            key=lambda document: document.sort_order,
        )
    )

    return PackageInput(
        authority_code=package.authority_code,
        name=package.name,
        documents=documents,
    )


def run_validation(
    db: Session,
    package_id: uuid.UUID,
    *,
    extracted_structure: dict[str, object] | None = None,
) -> ValidationRun:
    """Run one deterministic validation workflow."""

    package = db.scalar(
        select(FilingPackage)
        .options(selectinload(FilingPackage.documents))
        .where(FilingPackage.id == package_id)
    )

    if package is None:
        raise ValueError(f"Filing package {package_id} not found")

    validation_run = ValidationRun(
        package_id=package.id,
        authority_code=package.authority_code,
        status=ValidationRunStatus.RUNNING,
        current_stage="validation",
        started_at=datetime.now(timezone.utc),
    )

    package.status = PackageStatus.VALIDATING

    db.add(validation_run)
    db.commit()
    db.refresh(validation_run)

    try:
        if extracted_structure is not None:
            package_input = package_input_from_extracted_structure(
                package,
                extracted_structure,
            )
        else:
            package_input = _build_package_input(package)
        index_authority_rules(
            package.authority_code,
            db,
        )
        rules = get_indexed_rule_definitions(
            db,
            package.authority_code,
        )
        findings = validate_package(
            package_input,
            rules,
        )
        documents_by_filename = {
            document.filename: document.id
            for document in package.documents
        }

        orm_findings = map_findings_to_models(
            findings=findings,
            validation_run_id=validation_run.id,
            documents_by_filename=documents_by_filename,
        )

        db.add_all(orm_findings)

        requires_review = any(
            finding.result
            in (
                FindingResult.FAIL,
                FindingResult.INSUFFICIENT_EVIDENCE,
            )
            for finding in findings
        )

        validation_run.status = ValidationRunStatus.COMPLETED
        validation_run.current_stage = "completed"
        validation_run.completed_at = datetime.now(timezone.utc)

        package.status = (
            PackageStatus.AWAITING_APPROVAL
            if requires_review
            else PackageStatus.COMPLETED
        )

        db.commit()
        db.refresh(validation_run)

        return validation_run

    except Exception:
        db.rollback()

        failed_run = db.get(ValidationRun, validation_run.id)
        failed_package = db.get(FilingPackage, package.id)

        if failed_run is not None:
            failed_run.status = ValidationRunStatus.FAILED
            failed_run.current_stage = "failed"
            failed_run.completed_at = datetime.now(timezone.utc)

        if failed_package is not None:
            failed_package.status = PackageStatus.FAILED

        db.commit()

        raise