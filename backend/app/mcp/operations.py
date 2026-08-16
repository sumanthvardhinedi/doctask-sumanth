from __future__ import annotations

import json
import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.superdocs.client import SuperDocsClient
from app.mcp.errors import ToolFailure
from app.models.agent_workflow import AgentWorkflow
from app.models.filing import FilingPackage, PackageDocument
from app.models.finding import ApprovalDecision, Finding
from app.models.validation import ValidationRun
from app.services.agent_observability import build_agent_observability
from app.storage.document_store import DocumentStore
from app.validator.rules import get_rules_for_authority
from app.workflow.agent_workflow import (
    resume_agent_after_human_decision,
    start_or_resume_agent_workflow,
)
from app.workflow.superdocs_review import (
    SuperDocsReviewAlreadyExists,
    SuperDocsReviewError,
    decide_superdocs_review,
    export_superdocs_review,
    start_superdocs_review,
)


def jsonable(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def _parse_uuid(value: str, label: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ToolFailure("invalid_request", f"Invalid {label}") from exc


def _package_or_raise(db: Session, package_id: UUID) -> FilingPackage:
    package = db.get(FilingPackage, package_id)
    if package is None:
        raise ToolFailure("not_found", "Filing package not found")
    return package


def _run_or_raise(
    db: Session,
    package_id: UUID,
    validation_run_id: UUID,
) -> ValidationRun:
    validation_run = db.get(ValidationRun, validation_run_id)
    if validation_run is None or validation_run.package_id != package_id:
        raise ToolFailure("not_found", "Validation run not found")
    return validation_run


def _review_payload(review) -> dict:
    export_result = None
    if review.export_result_json:
        export_result = json.loads(review.export_result_json)

    proposed_changes: dict | list = {}
    if review.proposed_changes_json:
        proposed_changes = json.loads(review.proposed_changes_json)

    return jsonable(
        {
            "id": review.id,
            "package_id": review.package_id,
            "validation_run_id": review.validation_run_id,
            "finding_id": review.finding_id,
            "package_document_id": review.package_document_id,
            "status": review.status,
            "current_stage": review.current_stage,
            "edit_instruction": review.edit_instruction,
            "superdocs_session_id": review.superdocs_session_id,
            "job_id": review.job_id,
            "proposed_changes": proposed_changes,
            "export_result": export_result,
            "human_approved": review.human_approved,
            "human_notes": review.human_notes,
            "decided_at": review.decided_at,
        }
    )


def create_filing_package(db: Session, authority_code: str, name: str) -> dict:
    try:
        get_rules_for_authority(authority_code)
    except ValueError as exc:
        raise ToolFailure("invalid_request", str(exc)) from exc

    package = FilingPackage(authority_code=authority_code, name=name)
    db.add(package)
    db.commit()
    db.refresh(package)
    return jsonable(
        {
            "id": package.id,
            "authority_code": package.authority_code,
            "name": package.name,
            "status": package.status,
            "document_count": 0,
        }
    )


def add_package_document(
    db: Session,
    package_id: str,
    filename: str,
    content_type: str,
    file_size_bytes: int,
    storage_path: str,
    sort_order: int,
) -> dict:
    package = _package_or_raise(db, _parse_uuid(package_id, "package_id"))
    document = PackageDocument(
        package_id=package.id,
        filename=filename,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        storage_path=storage_path,
        sort_order=sort_order,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return jsonable(
        {
            "id": document.id,
            "package_id": document.package_id,
            "filename": document.filename,
            "content_type": document.content_type,
            "file_size_bytes": document.file_size_bytes,
            "storage_path": document.storage_path,
            "sort_order": document.sort_order,
        }
    )


def validate_filing_package(
    db: Session,
    package_id: str,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
) -> dict:
    package = _package_or_raise(db, _parse_uuid(package_id, "package_id"))
    try:
        validation_run = start_or_resume_agent_workflow(
            db,
            package.id,
            superdocs_client=superdocs_client,
            document_store=document_store,
        )
    except ValueError as exc:
        raise ToolFailure("failed", str(exc)) from exc
    return jsonable(
        {
            "id": validation_run.id,
            "package_id": validation_run.package_id,
            "status": validation_run.status,
            "started_at": validation_run.started_at,
            "completed_at": validation_run.completed_at,
        }
    )


def get_agent_workflow(db: Session, package_id: str) -> dict:
    package = _package_or_raise(db, _parse_uuid(package_id, "package_id"))
    workflow = db.scalar(
        select(AgentWorkflow)
        .where(AgentWorkflow.package_id == package.id)
        .order_by(AgentWorkflow.created_at.desc())
    )
    if workflow is None:
        raise ToolFailure("not_found", "Agent workflow not found")
    return jsonable(build_agent_observability(db, workflow))


def list_validation_runs(db: Session, package_id: str) -> dict:
    package = _package_or_raise(db, _parse_uuid(package_id, "package_id"))
    runs = db.scalars(
        select(ValidationRun)
        .where(ValidationRun.package_id == package.id)
        .order_by(ValidationRun.created_at.desc())
    ).all()
    return {
        "runs": jsonable(
            [
                {
                    "id": run.id,
                    "package_id": run.package_id,
                    "authority_code": run.authority_code,
                    "status": run.status,
                    "current_stage": run.current_stage,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                }
                for run in runs
            ]
        )
    }


def list_findings(db: Session, package_id: str, validation_run_id: str) -> dict:
    package_uuid = _parse_uuid(package_id, "package_id")
    _package_or_raise(db, package_uuid)
    run = _run_or_raise(
        db, package_uuid, _parse_uuid(validation_run_id, "validation_run_id")
    )
    findings = db.scalars(
        select(Finding)
        .where(Finding.validation_run_id == run.id)
        .order_by(Finding.created_at.asc())
    ).all()
    return {
        "findings": jsonable(
            [
                {
                    "id": finding.id,
                    "validation_run_id": finding.validation_run_id,
                    "package_document_id": finding.package_document_id,
                    "rule_id": finding.rule_id,
                    "rule_category": finding.rule_category,
                    "severity": finding.severity,
                    "result": finding.result,
                    "location": finding.location,
                    "evidence": finding.evidence,
                    "explanation": finding.explanation,
                    "is_hard_rejection": finding.is_hard_rejection,
                }
                for finding in findings
            ]
        )
    }


def decide_finding(
    db: Session,
    package_id: str,
    validation_run_id: str,
    finding_id: str,
    approved: bool,
    reviewer_notes: str | None = None,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
) -> dict:
    package_uuid = _parse_uuid(package_id, "package_id")
    _package_or_raise(db, package_uuid)
    run = _run_or_raise(
        db, package_uuid, _parse_uuid(validation_run_id, "validation_run_id")
    )
    finding = db.get(Finding, _parse_uuid(finding_id, "finding_id"))
    if finding is None or finding.validation_run_id != run.id:
        raise ToolFailure("not_found", "Finding not found")

    db.refresh(finding, attribute_names=["approval_decision"])
    if finding.approval_decision is not None:
        raise ToolFailure("conflict", "Finding already has an approval decision")

    decision = ApprovalDecision(
        finding_id=finding.id,
        approved=approved,
        reviewer_notes=reviewer_notes,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    resume_agent_after_human_decision(
        db,
        package_uuid,
        run.id,
        superdocs_client=superdocs_client,
        document_store=document_store,
    )
    return jsonable(
        {
            "id": decision.id,
            "finding_id": decision.finding_id,
            "approved": decision.approved,
            "reviewer_notes": decision.reviewer_notes,
            "decided_at": decision.decided_at,
        }
    )


def start_finding_superdocs_review(
    db: Session,
    package_id: str,
    validation_run_id: str,
    finding_id: str,
    *,
    superdocs_client: SuperDocsClient,
    document_store: DocumentStore,
) -> dict:
    package_uuid = _parse_uuid(package_id, "package_id")
    run_uuid = _parse_uuid(validation_run_id, "validation_run_id")
    finding_uuid = _parse_uuid(finding_id, "finding_id")
    try:
        review = start_superdocs_review(
            db,
            package_id=package_uuid,
            validation_run_id=run_uuid,
            finding_id=finding_uuid,
            client=superdocs_client,
            document_store=document_store,
        )
    except SuperDocsReviewAlreadyExists as exc:
        raise ToolFailure("conflict", str(exc)) from exc
    except SuperDocsReviewError as exc:
        message = str(exc)
        code = "not_found" if "not found" in message.lower() else "failed"
        raise ToolFailure(code, message) from exc

    resume_agent_after_human_decision(
        db,
        package_uuid,
        run_uuid,
        superdocs_client=superdocs_client,
        document_store=document_store,
    )
    return _review_payload(review)


def decide_finding_superdocs_review(
    db: Session,
    package_id: str,
    review_id: str,
    approved: bool,
    human_notes: str | None = None,
    *,
    superdocs_client: SuperDocsClient,
) -> dict:
    package_uuid = _parse_uuid(package_id, "package_id")
    review_uuid = _parse_uuid(review_id, "review_id")
    try:
        review = decide_superdocs_review(
            db,
            package_id=package_uuid,
            review_id=review_uuid,
            approved=approved,
            human_notes=human_notes,
            client=superdocs_client,
        )
    except SuperDocsReviewError as exc:
        message = str(exc)
        if "not found" in message.lower():
            code = "not_found"
        elif "already has a human decision" in message.lower():
            code = "conflict"
        else:
            code = "failed"
        raise ToolFailure(code, message) from exc

    resume_agent_after_human_decision(
        db,
        package_uuid,
        review.validation_run_id,
        superdocs_client=superdocs_client,
    )
    return _review_payload(review)


def export_finding_superdocs_review(
    db: Session,
    package_id: str,
    review_id: str,
    *,
    superdocs_client: SuperDocsClient,
) -> dict:
    package_uuid = _parse_uuid(package_id, "package_id")
    review_uuid = _parse_uuid(review_id, "review_id")
    try:
        review = export_superdocs_review(
            db,
            package_id=package_uuid,
            review_id=review_uuid,
            client=superdocs_client,
        )
    except SuperDocsReviewError as exc:
        message = str(exc)
        code = "not_found" if "not found" in message.lower() else "failed"
        raise ToolFailure(code, message) from exc

    resume_agent_after_human_decision(
        db,
        package_uuid,
        review.validation_run_id,
        superdocs_client=superdocs_client,
    )
    return _review_payload(review)


def default_document_store() -> DocumentStore:
    return DocumentStore(settings.uploads_root)
