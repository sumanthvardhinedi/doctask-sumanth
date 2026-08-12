from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.integrations.superdocs.client import SuperDocsClient
from app.integrations.superdocs.parsing import parse_proposed_changes
from app.models.enums import SuperDocsReviewStatus
from app.models.filing import FilingPackage, PackageDocument
from app.models.finding import Finding
from app.models.superdocs_review import SuperDocsReviewSession
from app.models.validation import ValidationRun
from app.services.edit_instruction import build_edit_instruction
from app.storage.document_store import DocumentStore

logger = logging.getLogger(__name__)


class SuperDocsReviewError(ValueError):
    """Domain error for SuperDocs-assisted review workflow."""


def _require_owned_finding(
    db: Session,
    *,
    package_id: uuid.UUID,
    validation_run_id: uuid.UUID,
    finding_id: uuid.UUID,
) -> tuple[FilingPackage, ValidationRun, Finding]:
    package = db.get(FilingPackage, package_id)
    if package is None:
        raise SuperDocsReviewError("Filing package not found")

    validation_run = db.get(ValidationRun, validation_run_id)
    if validation_run is None or validation_run.package_id != package_id:
        raise SuperDocsReviewError("Validation run not found")

    finding = db.get(Finding, finding_id)
    if finding is None or finding.validation_run_id != validation_run_id:
        raise SuperDocsReviewError("Finding not found")

    return package, validation_run, finding


def start_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    validation_run_id: uuid.UUID,
    finding_id: uuid.UUID,
    client: SuperDocsClient,
    document_store: DocumentStore,
) -> SuperDocsReviewSession:
    _, _, finding = _require_owned_finding(
        db,
        package_id=package_id,
        validation_run_id=validation_run_id,
        finding_id=finding_id,
    )

    existing = db.query(SuperDocsReviewSession).filter_by(finding_id=finding_id).first()
    if existing is not None:
        raise SuperDocsReviewError("SuperDocs review already exists for this finding")

    if finding.package_document_id is None:
        raise SuperDocsReviewError(
            "Finding has no associated package document for SuperDocs editing"
        )

    document = db.get(PackageDocument, finding.package_document_id)
    if document is None or document.package_id != package_id:
        raise SuperDocsReviewError("Package document not found for finding")

    try:
        content = document_store.read_bytes(document.storage_path)
    except FileNotFoundError as exc:
        raise SuperDocsReviewError(str(exc)) from exc
    except ValueError as exc:
        raise SuperDocsReviewError(str(exc)) from exc

    document_data: str | None
    try:
        document_data = content.decode("utf-8")
    except UnicodeDecodeError:
        document_data = None

    edit_instruction = build_edit_instruction(
        finding,
        document_filename=document.filename,
        document_data=document_data,
    )

    logger.info(
        "superdocs_review.start finding_id=%s document_id=%s",
        finding_id,
        document.id,
    )

    upload_result = client.upload(filename=document.filename, content=content)
    session_id = upload_result.get("session_id")
    if not session_id:
        raise SuperDocsReviewError("SuperDocs upload did not return session_id")

    chat_result = client.chat(session_id=session_id, message=edit_instruction)
    job_id = chat_result.get("job_id")
    if not job_id:
        raise SuperDocsReviewError("SuperDocs chat did not return job_id")

    if "proposed_changes" not in chat_result:
        raise SuperDocsReviewError("SuperDocs chat did not return proposed_changes")

    try:
        proposed = parse_proposed_changes(chat_result["proposed_changes"])
    except json.JSONDecodeError as exc:
        raise SuperDocsReviewError("Proposed changes were not valid JSON") from exc

    review = SuperDocsReviewSession(
        package_id=package_id,
        validation_run_id=validation_run_id,
        finding_id=finding_id,
        package_document_id=document.id,
        status=SuperDocsReviewStatus.PROPOSED,
        current_stage="proposed_changes",
        edit_instruction=edit_instruction,
        superdocs_session_id=session_id,
        job_id=job_id,
        proposed_changes_json=json.dumps(proposed),
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    logger.info(
        "superdocs_review.proposed review_id=%s job_id=%s",
        review.id,
        job_id,
    )
    return review


def decide_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    review_id: uuid.UUID,
    approved: bool,
    human_notes: str | None,
    client: SuperDocsClient,
) -> SuperDocsReviewSession:
    review = db.get(SuperDocsReviewSession, review_id)
    if review is None or review.package_id != package_id:
        raise SuperDocsReviewError("SuperDocs review not found")

    if review.status != SuperDocsReviewStatus.PROPOSED:
        raise SuperDocsReviewError(
            f"SuperDocs review cannot be decided from status '{review.status}'"
        )

    if review.human_approved is not None:
        raise SuperDocsReviewError("SuperDocs review already has a human decision")

    proposed = json.loads(review.proposed_changes_json)
    change_id = None
    changes = proposed.get("changes") if isinstance(proposed, dict) else None
    if isinstance(changes, list) and changes:
        first = changes[0]
        if isinstance(first, dict):
            change_id = first.get("change_id")

    review.human_approved = approved
    review.human_notes = human_notes
    review.decided_at = datetime.now(timezone.utc)
    review.current_stage = "human_decision"

    client.approve(
        session_id=review.superdocs_session_id,
        job_id=review.job_id,
        approved=approved,
        change_id=change_id,
        feedback=human_notes,
    )

    if approved:
        review.status = SuperDocsReviewStatus.APPROVED
        review.current_stage = "superdocs_approved"
    else:
        review.status = SuperDocsReviewStatus.REJECTED
        review.current_stage = "superdocs_rejected"

    db.commit()
    db.refresh(review)

    logger.info(
        "superdocs_review.decided review_id=%s approved=%s",
        review.id,
        approved,
    )
    return review


def export_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    review_id: uuid.UUID,
    client: SuperDocsClient,
) -> SuperDocsReviewSession:
    review = db.get(SuperDocsReviewSession, review_id)
    if review is None or review.package_id != package_id:
        raise SuperDocsReviewError("SuperDocs review not found")

    if review.status != SuperDocsReviewStatus.APPROVED:
        raise SuperDocsReviewError(
            "Export is only allowed after human approval and SuperDocs approve"
        )

    export_result = client.export(session_id=review.superdocs_session_id)
    review.export_result_json = json.dumps(export_result)
    review.status = SuperDocsReviewStatus.EXPORTED
    review.current_stage = "exported"

    db.commit()
    db.refresh(review)

    logger.info("superdocs_review.exported review_id=%s", review.id)
    return review
