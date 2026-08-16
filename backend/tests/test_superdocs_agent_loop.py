import sys
import uuid
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.models import (
    AgentStageCheckpoint,
    AgentStageCheckpointStatus,
    AgentWorkflow,
    AgentWorkflowStage,
    AgentWorkflowStatus,
    ApprovalDecision,
    FilingPackage,
    PackageDocument,
    PackageStatus,
    SuperDocsReviewSession,
    SuperDocsReviewStatus,
)
from app.services.rule_indexer import index_all_authorities
from app.services.superdocs_loop import evaluate_superdocs_loop
from app.storage.document_store import DocumentStore
from app.workflow.agent_workflow import start_or_resume_agent_workflow
from app.workflow.superdocs_review import decide_superdocs_review


@pytest.fixture()
def db() -> Session:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)

    try:
        with Session(engine) as session:
            index_all_authorities(session)
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)


class _Decision:
    def __init__(self, approved: bool | None) -> None:
        self.approved = approved


class _Finding:
    def __init__(
        self,
        finding_id: uuid.UUID,
        *,
        approved: bool | None,
        package_document_id: uuid.UUID | None,
    ) -> None:
        self.id = finding_id
        self.package_document_id = package_document_id
        self.approval_decision = None if approved is None else _Decision(approved)


class _Review:
    def __init__(
        self,
        finding_id: uuid.UUID,
        status: str,
        review_id: uuid.UUID | None = None,
    ) -> None:
        self.id = review_id or uuid.uuid4()
        self.finding_id = finding_id
        self.status = status


def test_rejected_finding_is_not_superdocs_eligible() -> None:
    finding_id = uuid.uuid4()
    result = evaluate_superdocs_loop(
        findings=[
            _Finding(
                finding_id,
                approved=False,
                package_document_id=uuid.uuid4(),
            )
        ],
        reviews=[],
    )

    assert result["eligible_count"] == 0
    assert result["pending_start"] == []
    assert result["ready_to_finalize"] is True


def test_approved_document_finding_waits_for_superdocs_start() -> None:
    finding_id = uuid.uuid4()
    result = evaluate_superdocs_loop(
        findings=[
            _Finding(
                finding_id,
                approved=True,
                package_document_id=uuid.uuid4(),
            )
        ],
        reviews=[],
    )

    assert result["pending_start"] == [str(finding_id)]
    assert result["loop_waiting"] is True
    assert result["ready_to_finalize"] is False


def test_rejected_superdocs_review_does_not_require_export() -> None:
    finding_id = uuid.uuid4()
    result = evaluate_superdocs_loop(
        findings=[
            _Finding(
                finding_id,
                approved=True,
                package_document_id=uuid.uuid4(),
            )
        ],
        reviews=[
            _Review(finding_id, SuperDocsReviewStatus.REJECTED),
        ],
    )

    assert result["rejected"] == [str(finding_id)]
    assert result["pending_export"] == []
    assert result["ready_to_finalize"] is True


def _mock_superdocs_client() -> Mock:
    client = Mock()
    client.upload.return_value = {
        "session_id": "session-123",
        "version_id": "version-1",
    }
    client.chat.return_value = {
        "job_id": "job-123",
        "proposed_changes": '{"changes": [{"change_id": "change-456"}]}',
    }
    client.approve.return_value = {"status": "approved", "job_id": "job-123"}
    client.export.return_value = {
        "status": "completed",
        "download_url": "https://example.com/file.docx",
    }
    return client


def _create_package(db: Session, uploads_dir: Path) -> FilingPackage:
    relative_path = "cover_letter.pdf"
    (uploads_dir / relative_path).write_bytes(b"<html>cover</html>")
    package = FilingPackage(
        id=uuid.uuid4(),
        authority_code="authority_a",
        name="SuperDocs agent package",
        status=PackageStatus.PENDING,
    )
    db.add(package)
    db.flush()
    db.add(
        PackageDocument(
            id=uuid.uuid4(),
            package_id=package.id,
            filename="cover_letter.pdf",
            content_type="application/pdf",
            file_size_bytes=100,
            storage_path=relative_path,
            sort_order=1,
        )
    )
    db.flush()
    return package


def test_agent_does_not_enter_superdocs_before_human_gate(
    db: Session,
    tmp_path: Path,
) -> None:
    package = _create_package(db, tmp_path)
    start_or_resume_agent_workflow(db, package.id)
    workflow = (
        db.query(AgentWorkflow)
        .filter(AgentWorkflow.package_id == package.id)
        .one()
    )
    stages = {
        checkpoint.stage
        for checkpoint in db.query(AgentStageCheckpoint).filter(
            AgentStageCheckpoint.workflow_id == workflow.id
        )
    }

    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert AgentWorkflowStage.HUMAN_REVIEW in stages
    assert AgentWorkflowStage.SUPERDOCS_REVIEW not in stages
    assert AgentWorkflowStage.FINALIZE_EXPORT not in stages


def test_superdocs_loop_starts_after_approvals_and_exports_only_when_approved(
    db: Session,
    tmp_path: Path,
) -> None:
    package = _create_package(db, tmp_path)
    start_or_resume_agent_workflow(db, package.id)
    workflow = (
        db.query(AgentWorkflow)
        .filter(AgentWorkflow.package_id == package.id)
        .one()
    )
    human_review = (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow.id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.HUMAN_REVIEW,
        )
        .one()
    )
    ingest = (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow.id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.INGEST_PACKAGE,
        )
        .one()
    )
    ingest_completed_at = ingest.completed_at

    for finding_id in human_review.output["pending_finding_ids"]:
        db.add(
            ApprovalDecision(
                finding_id=uuid.UUID(finding_id),
                approved=True,
            )
        )
    db.commit()

    client = _mock_superdocs_client()
    store = DocumentStore(tmp_path)
    start_or_resume_agent_workflow(
        db,
        package.id,
        superdocs_client=client,
        document_store=store,
    )
    db.refresh(workflow)
    superdocs = (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow.id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.SUPERDOCS_REVIEW,
        )
        .one()
    )

    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert superdocs.status == AgentStageCheckpointStatus.WAITING
    assert superdocs.token_count is None
    assert superdocs.output["pending_decision"]
    assert client.export.call_count == 0

    reviews = (
        db.query(SuperDocsReviewSession)
        .filter(SuperDocsReviewSession.package_id == package.id)
        .all()
    )
    assert reviews
    first, *rest = reviews
    pending_decision_ids = list(superdocs.output["pending_decision"])
    decide_superdocs_review(
        db,
        package_id=package.id,
        review_id=first.id,
        approved=False,
        human_notes="reject this item only",
        client=client,
    )
    for review in rest:
        decide_superdocs_review(
            db,
            package_id=package.id,
            review_id=review.id,
            approved=True,
            human_notes="approve",
            client=client,
        )

    start_or_resume_agent_workflow(
        db,
        package.id,
        superdocs_client=client,
        document_store=store,
    )
    db.refresh(workflow)
    db.refresh(ingest)
    db.refresh(first)
    finalize = (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow.id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.FINALIZE_EXPORT,
        )
        .one()
    )
    stored_package = db.get(FilingPackage, package.id)

    assert workflow.status == AgentWorkflowStatus.COMPLETED
    assert finalize.status == AgentStageCheckpointStatus.COMPLETED
    assert finalize.token_count is None
    assert str(first.id) in finalize.output["skipped_rejected_review_ids"]
    assert str(first.id) not in finalize.output["exported_review_ids"]
    assert first.status == SuperDocsReviewStatus.REJECTED
    assert first.export_result_json is None
    assert client.export.call_count == len(rest)
    assert ingest.completed_at == ingest_completed_at
    assert stored_package is not None
    assert stored_package.status == PackageStatus.COMPLETED
    assert pending_decision_ids
