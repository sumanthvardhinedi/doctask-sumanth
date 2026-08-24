from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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


class SuperDocsReviewAlreadyExists(SuperDocsReviewError):
    """Raised when a review already exists for the finding."""


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


def _get_existing_review(
    db: Session,
    finding_id: uuid.UUID,
) -> SuperDocsReviewSession | None:
    return db.scalars(
        select(SuperDocsReviewSession).where(
            SuperDocsReviewSession.finding_id == finding_id
        )
    ).first()


def _mark_review_failed(
    db: Session,
    review: SuperDocsReviewSession,
    *,
    stage: str,
) -> None:
    review.status = SuperDocsReviewStatus.FAILED
    review.current_stage = stage

    try:
        db.commit()
        db.refresh(review)
    except Exception:
        db.rollback()

        logger.exception(
            "superdocs_review.failed_checkpoint_error review_id=%s stage=%s",
            review.id,
            stage,
        )


def _load_review_document(
    db: Session,
    *,
    package_id: uuid.UUID,
    finding: Finding,
    document_store: DocumentStore,
) -> tuple[PackageDocument, bytes, str | None]:
    if finding.package_document_id is None:
        raise SuperDocsReviewError(
            "Finding has no associated package document for SuperDocs editing"
        )

    document = db.get(
        PackageDocument,
        finding.package_document_id,
    )

    if document is None or document.package_id != package_id:
        raise SuperDocsReviewError(
            "Package document not found for finding"
        )

    try:
        content = document_store.read_bytes(
            document.storage_path,
        )
    except FileNotFoundError as exc:
        raise SuperDocsReviewError(str(exc)) from exc
    except ValueError as exc:
        raise SuperDocsReviewError(str(exc)) from exc

    try:
        document_data = content.decode("utf-8")
    except UnicodeDecodeError:
        document_data = None

    return document, content, document_data


def _extract_change_id(
    proposed: object,
) -> str | None:
    if not isinstance(proposed, dict):
        return None

    changes = proposed.get("changes")

    if not isinstance(changes, list) or not changes:
        return None

    first = changes[0]

    if not isinstance(first, dict):
        return None

    change_id = first.get("change_id")

    if isinstance(change_id, str):
        return change_id

    return None


def _continue_uploaded_review(
    db: Session,
    *,
    review: SuperDocsReviewSession,
    client: SuperDocsClient,
) -> SuperDocsReviewSession:
    """
    Resume a review that has already reached the uploaded checkpoint.

    The SuperDocs session ID must already exist.
    """

    if not review.superdocs_session_id:
        _mark_review_failed(
            db,
            review,
            stage="chat_failed",
        )

        raise SuperDocsReviewError(
            "Uploaded SuperDocs review has no session_id"
        )

    try:
        chat_result = client.chat(
            session_id=review.superdocs_session_id,
            message=review.edit_instruction,
        )
    except Exception as exc:
        logger.exception(
            "superdocs_review.chat_failed review_id=%s",
            review.id,
        )

        _mark_review_failed(
            db,
            review,
            stage="chat_failed",
        )

        raise SuperDocsReviewError(
            "SuperDocs chat failed"
        ) from exc

    job_id = chat_result.get("job_id")

    if not job_id:
        _mark_review_failed(
            db,
            review,
            stage="chat_failed",
        )

        raise SuperDocsReviewError(
            "SuperDocs chat did not return job_id"
        )

    if "proposed_changes" not in chat_result:
        _mark_review_failed(
            db,
            review,
            stage="chat_failed",
        )

        raise SuperDocsReviewError(
            "SuperDocs chat did not return proposed_changes"
        )

    try:
        proposed = parse_proposed_changes(
            chat_result["proposed_changes"]
        )
    except json.JSONDecodeError as exc:
        _mark_review_failed(
            db,
            review,
            stage="proposed_changes_failed",
        )

        raise SuperDocsReviewError(
            "Proposed changes were not valid JSON"
        ) from exc

    review.job_id = job_id
    review.proposed_changes_json = json.dumps(proposed)
    review.status = SuperDocsReviewStatus.PROPOSED
    review.current_stage = "proposed_changes"

    db.commit()
    db.refresh(review)

    logger.info(
        "superdocs_review.proposed review_id=%s job_id=%s",
        review.id,
        job_id,
    )

    return review
def start_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    validation_run_id: uuid.UUID,
    finding_id: uuid.UUID,
    client: SuperDocsClient,
    document_store: DocumentStore,
) -> SuperDocsReviewSession:
    """
    Start or resume a SuperDocs-assisted review.

    Phase 2E guarantees:

    - one durable review session per finding
    - concurrent initial requests cannot duplicate the upload
    - the durable CREATING checkpoint is written before upload
    - UPLOADED checkpoints resume at chat
    - CREATING checkpoints with a SuperDocs session resume at chat
    - FAILED checkpoints can be retried
    - completed states are idempotent
    """

    _, _, finding = _require_owned_finding(
        db,
        package_id=package_id,
        validation_run_id=validation_run_id,
        finding_id=finding_id,
    )

    # ---------------------------------------------------------
    # Resolve the document and trusted edit instruction.
    # ---------------------------------------------------------

    if finding.package_document_id is None:
        raise SuperDocsReviewError(
            "Finding has no associated package document for SuperDocs editing"
        )

    document = db.get(
        PackageDocument,
        finding.package_document_id,
    )

    if document is None or document.package_id != package_id:
        raise SuperDocsReviewError(
            "Package document not found for finding"
        )

    try:
        content = document_store.read_bytes(
            document.storage_path
        )
    except FileNotFoundError as exc:
        raise SuperDocsReviewError(str(exc)) from exc
    except ValueError as exc:
        raise SuperDocsReviewError(str(exc)) from exc

    try:
        document_data = content.decode("utf-8")
    except UnicodeDecodeError:
        document_data = None

    edit_instruction = build_edit_instruction(
        finding,
        document_filename=document.filename,
        document_data=document_data,
    )

    # ---------------------------------------------------------
    # Existing workflow.
    # ---------------------------------------------------------

    existing = _get_existing_review(
        db,
        finding_id,
    )

    if existing is not None:

        # Completed workflow is idempotent.
        if existing.status in {
            SuperDocsReviewStatus.PROPOSED,
            SuperDocsReviewStatus.APPROVED,
            SuperDocsReviewStatus.REJECTED,
            SuperDocsReviewStatus.EXPORTED,
        }:
            logger.info(
                "superdocs_review.idempotent_existing "
                "finding_id=%s review_id=%s status=%s",
                finding_id,
                existing.id,
                existing.status,
            )
            return existing

        # A durable upload checkpoint can continue at chat.
        if existing.status == SuperDocsReviewStatus.UPLOADED:
            logger.info(
                "superdocs_review.resume_uploaded "
                "finding_id=%s review_id=%s",
                finding_id,
                existing.id,
            )

            return _continue_uploaded_review(
                db,
                review=existing,
                client=client,
            )

        # CREATING with an existing SuperDocs session means upload
        # already succeeded but the checkpoint was not advanced.
        if (
            existing.status == SuperDocsReviewStatus.CREATING
            and existing.superdocs_session_id
        ):
            logger.info(
                "superdocs_review.resume_creating_with_session "
                "finding_id=%s review_id=%s",
                finding_id,
                existing.id,
            )

            existing.status = SuperDocsReviewStatus.UPLOADED
            existing.current_stage = "uploaded"

            db.commit()
            db.refresh(existing)

            return _continue_uploaded_review(
                db,
                review=existing,
                client=client,
            )

        # A CREATING record without a SuperDocs session is an active
        # creation owned by another concurrent request.
        if (
            existing.status == SuperDocsReviewStatus.CREATING
            and not existing.superdocs_session_id
        ):
            raise SuperDocsReviewAlreadyExists(
                "SuperDocs review is already being created for this finding"
            )

        # FAILED is explicitly resumable.
        if existing.status == SuperDocsReviewStatus.FAILED:
            logger.info(
                "superdocs_review.retry_failed "
                "finding_id=%s review_id=%s stage=%s",
                finding_id,
                existing.id,
                existing.current_stage,
            )

            # If upload already succeeded, never upload again.
            if existing.superdocs_session_id:
                existing.status = SuperDocsReviewStatus.UPLOADED
                existing.current_stage = "uploaded"

                db.commit()
                db.refresh(existing)

                return _continue_uploaded_review(
                    db,
                    review=existing,
                    client=client,
                )

            # Otherwise retry from upload.
            existing.status = SuperDocsReviewStatus.CREATING
            existing.current_stage = "creating"
            existing.edit_instruction = edit_instruction
            existing.package_document_id = document.id

            db.commit()
            db.refresh(existing)

            review = existing

        else:
            raise SuperDocsReviewError(
                f"SuperDocs review cannot be resumed from status "
                f"'{existing.status}'"
            )

    else:
        # -----------------------------------------------------
        # IMPORTANT:
        #
        # Persist CREATING BEFORE calling SuperDocs.
        #
        # This is what makes the initial upload idempotent.
        # -----------------------------------------------------

        review = SuperDocsReviewSession(
            package_id=package_id,
            validation_run_id=validation_run_id,
            finding_id=finding_id,
            package_document_id=document.id,
            status=SuperDocsReviewStatus.CREATING,
            current_stage="creating",
            edit_instruction=edit_instruction,
            superdocs_session_id=None,
            job_id=None,
            proposed_changes_json=None,
            export_result_json=None,
            human_approved=None,
            human_notes=None,
        )

        db.add(review)

        try:
            db.commit()
            db.refresh(review)

        except IntegrityError as exc:
            db.rollback()

            # Another request won the unique finding_id race.
            existing = _get_existing_review(
                db,
                finding_id,
            )

            if existing is not None:
                if (
                    existing.status
                    == SuperDocsReviewStatus.CREATING
                    and not existing.superdocs_session_id
                ):
                    raise SuperDocsReviewAlreadyExists(
                        "SuperDocs review is already being created "
                        "for this finding"
                    ) from exc

                if existing.status in {
                    SuperDocsReviewStatus.PROPOSED,
                    SuperDocsReviewStatus.APPROVED,
                    SuperDocsReviewStatus.REJECTED,
                    SuperDocsReviewStatus.EXPORTED,
                }:
                    return existing

                if (
                    existing.status == SuperDocsReviewStatus.UPLOADED
                    or existing.superdocs_session_id
                ):
                    return _continue_uploaded_review(
                        db,
                        review=existing,
                        client=client,
                    )

            raise SuperDocsReviewError(
                "Could not create SuperDocs review"
            ) from exc

    # ---------------------------------------------------------
    # Only the request that owns the CREATING checkpoint
    # reaches the external upload boundary.
    # ---------------------------------------------------------

    logger.info(
        "superdocs_review.upload_start "
        "finding_id=%s review_id=%s",
        finding_id,
        review.id,
    )

    try:
        upload_session_id = str(uuid.uuid4())
        upload_result = client.upload(
            filename=document.filename,
            content=content,
            session_id=upload_session_id,
)

    except Exception as exc:
        logger.exception(
            "superdocs_review.upload_failed "
            "finding_id=%s review_id=%s",
            finding_id,
            review.id,
        )

        _mark_review_failed(
            db,
            review,
            stage="upload_failed",
        )

        raise SuperDocsReviewError(
            "SuperDocs upload failed"
        ) from exc

    session_id = upload_result.get("session_id")

    if not session_id:
        _mark_review_failed(
            db,
            review,
            stage="upload_failed",
        )

        raise SuperDocsReviewError(
            "SuperDocs upload did not return session_id"
        )

    # ---------------------------------------------------------
    # Durable UPLOADED checkpoint.
    #
    # If chat fails after this point, retry can continue without
    # uploading the document again.
    # ---------------------------------------------------------

    review.superdocs_session_id = session_id
    review.status = SuperDocsReviewStatus.UPLOADED
    review.current_stage = "uploaded"

    db.commit()
    db.refresh(review)

    logger.info(
        "superdocs_review.uploaded "
        "finding_id=%s review_id=%s session_id=%s",
        finding_id,
        review.id,
        session_id,
    )

    # ---------------------------------------------------------
    # Continue from uploaded checkpoint.
    # ---------------------------------------------------------

    return _continue_uploaded_review(
        db,
        review=review,
        client=client,
    )
def decide_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    review_id: uuid.UUID,
    approved: bool,
    human_notes: str | None,
    client: SuperDocsClient,
) -> SuperDocsReviewSession:
    review = db.get(
        SuperDocsReviewSession,
        review_id,
    )

    if review is None or review.package_id != package_id:
        raise SuperDocsReviewError(
            "SuperDocs review not found"
        )

    if review.status != SuperDocsReviewStatus.PROPOSED:
        raise SuperDocsReviewError(
            f"SuperDocs review cannot be decided from status "
            f"'{review.status}'"
        )

    # Lock persisted review before checking/updating decision.
    locked_review = db.scalars(
        select(SuperDocsReviewSession)
        .where(SuperDocsReviewSession.id == review_id)
        .with_for_update()
    ).one()

    if locked_review.human_approved is not None:
        db.rollback()

        raise SuperDocsReviewError(
            "SuperDocs review already has a human decision"
        )

    if not locked_review.proposed_changes_json:
        db.rollback()

        raise SuperDocsReviewError(
            "SuperDocs review has no proposed changes"
        )

    proposed = json.loads(
        locked_review.proposed_changes_json
    )

    change_id = _extract_change_id(
        proposed,
    )

    locked_review.human_approved = approved
    locked_review.human_notes = human_notes
    locked_review.decided_at = datetime.now(timezone.utc)
    locked_review.current_stage = "human_decision"

    if approved:
        try:
            client.approve(
                session_id=locked_review.superdocs_session_id,
                job_id=locked_review.job_id,
                approved=True,
                change_id=change_id,
                feedback=human_notes,
            )
        except Exception as exc:
            db.rollback()

            logger.exception(
                "superdocs_review.approve_failed "
                "review_id=%s approved=%s",
                review_id,
                approved,
            )

            raise SuperDocsReviewError(
                "SuperDocs approve failed"
            ) from exc

        locked_review.status = SuperDocsReviewStatus.APPROVED
        locked_review.current_stage = "superdocs_approved"

    else:
        # Rejection is terminal.
        # NEVER call SuperDocs approve() for a rejection.
        locked_review.status = SuperDocsReviewStatus.REJECTED
        locked_review.current_stage = "superdocs_rejected"

    db.commit()
    db.refresh(locked_review)

    logger.info(
        "superdocs_review.decided review_id=%s approved=%s",
        locked_review.id,
        approved,
    )

    return locked_review


def export_superdocs_review(
    db: Session,
    *,
    package_id: uuid.UUID,
    review_id: uuid.UUID,
    client: SuperDocsClient,
) -> SuperDocsReviewSession:
    review = db.get(
        SuperDocsReviewSession,
        review_id,
    )

    if review is None or review.package_id != package_id:
        raise SuperDocsReviewError(
            "SuperDocs review not found"
        )

    if review.status == SuperDocsReviewStatus.EXPORTED:
        return review

    if review.status != SuperDocsReviewStatus.APPROVED:
        raise SuperDocsReviewError(
            "Export is only allowed after human approval and SuperDocs approve"
        )

    # Lock the review so two export requests cannot transition
    # the same review twice.
    locked_review = db.scalars(
        select(SuperDocsReviewSession)
        .where(SuperDocsReviewSession.id == review_id)
        .with_for_update()
    ).one()

    if locked_review.status == SuperDocsReviewStatus.EXPORTED:
        return locked_review

    if locked_review.status != SuperDocsReviewStatus.APPROVED:
        db.rollback()

        raise SuperDocsReviewError(
            "Export is only allowed after human approval and SuperDocs approve"
        )

    try:
        export_result = client.export(
            session_id=locked_review.superdocs_session_id,
        )
    except Exception as exc:
        db.rollback()

        logger.exception(
            "superdocs_review.export_failed review_id=%s",
            review_id,
        )

        raise SuperDocsReviewError(
            "SuperDocs export failed"
        ) from exc

    locked_review.export_result_json = json.dumps(
        export_result
    )
    locked_review.status = SuperDocsReviewStatus.EXPORTED
    locked_review.current_stage = "exported"

    db.commit()
    db.refresh(locked_review)

    logger.info(
        "superdocs_review.exported review_id=%s",
        locked_review.id,
    )

    return locked_review