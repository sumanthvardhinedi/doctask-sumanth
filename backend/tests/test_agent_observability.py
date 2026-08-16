import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.main import app
from app.models import (
    AgentStageCheckpointStatus,
    AgentWorkflow,
    AgentWorkflowStage,
    AgentWorkflowStatus,
    FilingPackage,
    Finding,
    PackageDocument,
    PackageStatus,
    SuperDocsReviewSession,
    SuperDocsReviewStatus,
)
from app.services.agent_observability import (
    build_agent_observability,
    duration_ms,
)
from app.services.rule_indexer import index_all_authorities
from app.workflow.agent_workflow import start_or_resume_agent_workflow

client = TestClient(app)


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


def _create_package(
    db: Session,
    *,
    authority_code: str = "authority_a",
    with_document: bool = True,
) -> FilingPackage:
    package = FilingPackage(
        id=uuid.uuid4(),
        authority_code=authority_code,
        name="Observability test package",
        status=PackageStatus.PENDING,
    )
    db.add(package)
    db.flush()
    if with_document:
        db.add(
            PackageDocument(
                id=uuid.uuid4(),
                package_id=package.id,
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                storage_path="test/cover_letter.pdf",
                sort_order=1,
            )
        )
        db.flush()
    return package


def _workflow(db: Session, package_id: uuid.UUID) -> AgentWorkflow:
    workflow = (
        db.query(AgentWorkflow)
        .filter(AgentWorkflow.package_id == package_id)
        .order_by(AgentWorkflow.created_at.desc())
        .first()
    )
    assert workflow is not None
    return workflow


def test_duration_ms_is_none_until_both_timestamps_exist() -> None:
    start = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    assert duration_ms(None, start) is None
    assert duration_ms(start, None) is None
    assert duration_ms(start, start + timedelta(seconds=1.5)) == 1500


def test_waiting_workflow_exposes_stage_timing_without_invented_cost(
    db: Session,
) -> None:
    package = _create_package(db)
    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow(db, package.id)

    snapshot = build_agent_observability(db, workflow)

    assert snapshot["status"] == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert snapshot["total_duration_ms"] is None
    assert snapshot["completed_at"] is None
    assert snapshot["paused_at"] is not None
    assert snapshot["elapsed_ms"] is not None
    assert snapshot["elapsed_ms"] >= 0
    assert snapshot["retry_count"] == 0
    assert snapshot["token_count"] is None
    assert snapshot["estimated_cost"] is None
    assert snapshot["api_operations"] == []
    assert snapshot["waiting_stage_count"] == 1
    assert snapshot["failed_stage_count"] == 0
    assert snapshot["completed_stage_count"] >= 1

    ingest = next(
        stage
        for stage in snapshot["stages"]
        if stage["stage"] == AgentWorkflowStage.INGEST_PACKAGE
    )
    assert ingest["status"] == AgentStageCheckpointStatus.COMPLETED
    assert ingest["started_at"] is not None
    assert ingest["completed_at"] is not None
    assert ingest["duration_ms"] is not None
    assert ingest["duration_ms"] >= 0
    assert ingest["token_count"] is None
    assert ingest["estimated_cost"] is None

    human_review = next(
        stage
        for stage in snapshot["stages"]
        if stage["stage"] == AgentWorkflowStage.HUMAN_REVIEW
    )
    assert human_review["status"] == AgentStageCheckpointStatus.WAITING
    assert human_review["completed_at"] is None
    assert human_review["duration_ms"] is None
    assert human_review["elapsed_ms"] is not None
    assert human_review["elapsed_ms"] >= 0


def test_failed_workflow_records_failure_and_retries(db: Session) -> None:
    package = _create_package(db, authority_code="unknown_authority")
    package_id = package.id

    with pytest.raises(ValueError):
        start_or_resume_agent_workflow(db, package_id)

    workflow = _workflow(db, package_id)
    first = build_agent_observability(db, workflow)

    assert first["status"] == AgentWorkflowStatus.FAILED
    assert first["retry_count"] == 0
    assert first["error"] is not None
    assert first["failed_stage_count"] == 1
    assert first["total_duration_ms"] is not None
    assert first["total_duration_ms"] >= 0
    failed_stage = next(
        stage for stage in first["stages"] if stage["status"] == "failed"
    )
    assert failed_stage["stage"] == AgentWorkflowStage.CLASSIFY_DOCUMENTS
    assert failed_stage["error"] is not None
    assert failed_stage["token_count"] is None

    with pytest.raises(ValueError):
        start_or_resume_agent_workflow(db, package_id)

    db.refresh(workflow)
    retried = build_agent_observability(db, workflow)
    assert retried["retry_count"] == 1
    assert retried["status"] == AgentWorkflowStatus.FAILED


def test_superdocs_api_operations_count_persisted_sessions_only(
    db: Session,
) -> None:
    package = _create_package(db)
    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow(db, package.id)

    finding = (
        db.query(Finding)
        .filter(Finding.validation_run_id == workflow.validation_run_id)
        .first()
    )
    document = (
        db.query(PackageDocument)
        .filter(PackageDocument.package_id == package.id)
        .one()
    )
    assert finding is not None

    db.add(
        SuperDocsReviewSession(
            package_id=package.id,
            validation_run_id=workflow.validation_run_id,
            finding_id=finding.id,
            package_document_id=document.id,
            status=SuperDocsReviewStatus.EXPORTED,
            edit_instruction="Apply the published finding explanation.",
            superdocs_session_id="session-obs",
        )
    )
    db.commit()

    snapshot = build_agent_observability(db, workflow)
    assert snapshot["api_operations"] == [
        {"provider": "superdocs", "operation": "session", "count": 1},
        {"provider": "superdocs", "operation": "export", "count": 1},
    ]
    assert snapshot["estimated_cost"] is None
    assert snapshot["token_count"] is None


def test_agent_workflow_observability_endpoint(db: Session) -> None:
    missing_package = uuid.uuid4()
    missing = client.get(f"/api/v1/packages/{missing_package}/agent-workflow")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Filing package not found"

    package = _create_package(db)
    db.commit()
    no_workflow = client.get(f"/api/v1/packages/{package.id}/agent-workflow")
    assert no_workflow.status_code == 404
    assert no_workflow.json()["detail"] == "Agent workflow not found"

    start_or_resume_agent_workflow(db, package.id)
    response = client.get(f"/api/v1/packages/{package.id}/agent-workflow")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert body["token_count"] is None
    assert body["estimated_cost"] is None
    assert body["total_duration_ms"] is None
    assert any(
        stage["stage"] == AgentWorkflowStage.HUMAN_REVIEW
        and stage["status"] == AgentStageCheckpointStatus.WAITING
        for stage in body["stages"]
    )
