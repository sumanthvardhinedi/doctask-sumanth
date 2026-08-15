import sys
import uuid
from pathlib import Path

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
    FilingPackage,
    PackageDocument,
    PackageStatus,
    ValidationRun,
    ValidationRunStatus,
)
from app.services.rule_indexer import index_all_authorities
from app.workflow.agent_workflow import (
    apply_workflow_status,
    start_or_resume_agent_workflow,
)


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
    with_document: bool = False,
) -> FilingPackage:
    package = FilingPackage(
        id=uuid.uuid4(),
        authority_code=authority_code,
        name="Agent workflow test package",
        status=PackageStatus.PENDING,
    )
    db.add(package)
    db.flush()

    if with_document:
        document = PackageDocument(
            id=uuid.uuid4(),
            package_id=package.id,
            filename="cover_letter.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
            storage_path="test/cover_letter.pdf",
            sort_order=1,
        )
        db.add(document)
        db.flush()

    return package


def _workflow_for_package(db: Session, package_id: uuid.UUID) -> AgentWorkflow:
    workflow = (
        db.query(AgentWorkflow)
        .filter(AgentWorkflow.package_id == package_id)
        .order_by(AgentWorkflow.created_at.desc())
        .first()
    )
    assert workflow is not None
    return workflow


def test_agent_workflow_creates_persisted_state(db: Session) -> None:
    package = _create_package(db)

    run = start_or_resume_agent_workflow(db, package.id)

    assert run.status == ValidationRunStatus.COMPLETED

    workflow = _workflow_for_package(db, package.id)

    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert workflow.validation_run_id == run.id
    assert workflow.current_stage == AgentWorkflowStage.HUMAN_REVIEW
    assert workflow.started_at is not None
    assert workflow.completed_at is not None


def test_agent_workflow_records_stage_transitions(db: Session) -> None:
    package = _create_package(db)

    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow_for_package(db, package.id)

    checkpoints = (
        db.query(AgentStageCheckpoint)
        .filter(AgentStageCheckpoint.workflow_id == workflow.id)
        .all()
    )
    stages = [
        checkpoint.stage
        for checkpoint in sorted(
            checkpoints,
            key=lambda item: item.started_at or item.created_at,
        )
    ]

    assert stages == [
        AgentWorkflowStage.INGEST_PACKAGE,
        AgentWorkflowStage.CLASSIFY_DOCUMENTS,
        AgentWorkflowStage.EXTRACT_STRUCTURE,
        AgentWorkflowStage.LOAD_AUTHORITY_RULES,
        AgentWorkflowStage.VALIDATE_PACKAGE,
        AgentWorkflowStage.GENERATE_FINDINGS,
        AgentWorkflowStage.HUMAN_REVIEW,
    ]


def test_agent_workflow_persists_checkpoints_without_invented_tokens(
    db: Session,
) -> None:
    package = _create_package(db, with_document=True)

    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow_for_package(db, package.id)

    checkpoints = (
        db.query(AgentStageCheckpoint)
        .filter(AgentStageCheckpoint.workflow_id == workflow.id)
        .all()
    )

    assert len(checkpoints) == 7

    ingest = next(
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.stage == AgentWorkflowStage.INGEST_PACKAGE
    )
    load_rules = next(
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.stage == AgentWorkflowStage.LOAD_AUTHORITY_RULES
    )

    assert ingest.status == AgentStageCheckpointStatus.COMPLETED
    assert ingest.output is not None
    assert ingest.output["document_count"] == 1
    assert load_rules.output is not None
    assert load_rules.output["rule_count"] == 8

    for checkpoint in checkpoints:
        assert checkpoint.token_count is None
        assert checkpoint.estimated_cost is None
        assert checkpoint.model_provider is None
        assert checkpoint.model_operation is None


def test_agent_workflow_resume_skips_completed_stages(db: Session) -> None:
    package = _create_package(db)

    first_run = start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow_for_package(db, package.id)
    ingest = next(
        checkpoint
        for checkpoint in workflow.checkpoints
        if checkpoint.stage == AgentWorkflowStage.INGEST_PACKAGE
    )
    ingest_completed_at = ingest.completed_at

    second_run = start_or_resume_agent_workflow(db, package.id)

    assert second_run.id == first_run.id

    runs = (
        db.query(ValidationRun)
        .filter(ValidationRun.package_id == package.id)
        .all()
    )
    assert len(runs) == 1

    db.refresh(ingest)
    assert ingest.completed_at == ingest_completed_at


def test_agent_workflow_terminal_waiting_for_human(db: Session) -> None:
    package = _create_package(db)

    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow_for_package(db, package.id)

    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN

    stored_package = db.get(FilingPackage, package.id)
    assert stored_package is not None
    assert stored_package.status == PackageStatus.AWAITING_APPROVAL


def test_invalid_workflow_transition_is_rejected(db: Session) -> None:
    package = _create_package(db)
    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow_for_package(db, package.id)

    with pytest.raises(ValueError, match="Invalid workflow transition"):
        apply_workflow_status(workflow, AgentWorkflowStatus.RUNNING)


def test_agent_workflow_missing_package_fails(db: Session) -> None:
    missing_id = uuid.uuid4()

    with pytest.raises(ValueError, match="not found"):
        start_or_resume_agent_workflow(db, missing_id)


def test_agent_workflow_unknown_authority_marks_failed(db: Session) -> None:
    package = _create_package(db, authority_code="unknown_authority")
    package_id = package.id

    with pytest.raises(ValueError):
        start_or_resume_agent_workflow(db, package_id)

    workflow = _workflow_for_package(db, package_id)

    assert workflow.status == AgentWorkflowStatus.FAILED
    assert workflow.current_stage == AgentWorkflowStage.CLASSIFY_DOCUMENTS
    assert workflow.error is not None
