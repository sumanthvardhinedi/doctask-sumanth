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
    ApprovalDecision,
    FilingPackage,
    Finding,
    FindingResult,
    PackageDocument,
    PackageStatus,
)
from app.services.human_review_gate import evaluate_human_review_gate
from app.services.rule_indexer import index_all_authorities
from app.workflow.agent_workflow import start_or_resume_agent_workflow


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


def test_rejecting_one_finding_does_not_decide_another() -> None:
    gate = evaluate_human_review_gate(
        findings=[
            {
                "finding_id": "a",
                "rule_id": "rule.a",
                "result": FindingResult.FAIL,
                "approved": False,
            },
            {
                "finding_id": "b",
                "rule_id": "rule.b",
                "result": FindingResult.FAIL,
                "approved": None,
            },
        ]
    )

    assert gate["rejected_finding_ids"] == ["a"]
    assert gate["pending_finding_ids"] == ["b"]
    assert gate["gate_satisfied"] is False


def test_pass_finding_is_not_reviewable_unless_conflicted() -> None:
    without_conflict = evaluate_human_review_gate(
        findings=[
            {
                "finding_id": "p",
                "rule_id": "signature.cover_letter",
                "result": FindingResult.PASS,
                "approved": None,
            }
        ]
    )
    with_conflict = evaluate_human_review_gate(
        findings=[
            {
                "finding_id": "p",
                "rule_id": "signature.cover_letter",
                "result": FindingResult.PASS,
                "approved": None,
            }
        ],
        conflict_rule_ids=["signature.cover_letter"],
    )

    assert without_conflict["gate_satisfied"] is True
    assert without_conflict["pending_count"] == 0
    assert with_conflict["gate_satisfied"] is False
    assert with_conflict["pending_finding_ids"] == ["p"]


def test_gate_satisfied_when_all_reviewable_items_decided() -> None:
    gate = evaluate_human_review_gate(
        findings=[
            {
                "finding_id": "a",
                "rule_id": "rule.a",
                "result": FindingResult.FAIL,
                "approved": False,
            },
            {
                "finding_id": "b",
                "rule_id": "rule.b",
                "result": FindingResult.INSUFFICIENT_EVIDENCE,
                "approved": True,
            },
            {
                "finding_id": "c",
                "rule_id": "rule.c",
                "result": FindingResult.PASS,
                "approved": None,
            },
        ]
    )

    assert gate["gate_satisfied"] is True
    assert gate["approved_finding_ids"] == ["b"]
    assert gate["rejected_finding_ids"] == ["a"]


def _create_package(db: Session) -> FilingPackage:
    package = FilingPackage(
        id=uuid.uuid4(),
        authority_code="authority_a",
        name="Human review package",
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
        .one()
    )
    return workflow


def _human_review_checkpoint(
    db: Session, workflow_id: uuid.UUID
) -> AgentStageCheckpoint:
    return (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow_id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.HUMAN_REVIEW,
        )
        .one()
    )


def test_agent_parks_human_review_until_each_item_is_decided(db: Session) -> None:
    package = _create_package(db)
    start_or_resume_agent_workflow(db, package.id)
    workflow = _workflow(db, package.id)
    checkpoint = _human_review_checkpoint(db, workflow.id)

    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert checkpoint.status == AgentStageCheckpointStatus.WAITING
    assert checkpoint.completed_at is None
    assert checkpoint.token_count is None
    assert checkpoint.output["gate_satisfied"] is False
    pending_ids = list(checkpoint.output["pending_finding_ids"])
    assert len(pending_ids) >= 2

    first_id = uuid.UUID(pending_ids[0])
    second_id = uuid.UUID(pending_ids[1])
    db.add(ApprovalDecision(finding_id=first_id, approved=False, reviewer_notes="no"))
    db.commit()

    start_or_resume_agent_workflow(db, package.id)
    db.refresh(workflow)
    db.refresh(checkpoint)
    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert str(second_id) in checkpoint.output["pending_finding_ids"]
    assert str(first_id) in checkpoint.output["rejected_finding_ids"]
    assert str(second_id) not in checkpoint.output["rejected_finding_ids"]

    remaining = list(checkpoint.output["pending_finding_ids"])
    for finding_id in remaining:
        db.add(
            ApprovalDecision(
                finding_id=uuid.UUID(finding_id),
                approved=True,
                reviewer_notes="ok",
            )
        )
    db.commit()

    ingest = next(
        item
        for item in workflow.checkpoints
        if item.stage == AgentWorkflowStage.INGEST_PACKAGE
    )
    ingest_completed_at = ingest.completed_at

    start_or_resume_agent_workflow(db, package.id)
    db.refresh(workflow)
    db.refresh(checkpoint)
    db.refresh(ingest)
    human_review = _human_review_checkpoint(db, workflow.id)
    superdocs = (
        db.query(AgentStageCheckpoint)
        .filter(
            AgentStageCheckpoint.workflow_id == workflow.id,
            AgentStageCheckpoint.stage == AgentWorkflowStage.SUPERDOCS_REVIEW,
        )
        .one()
    )

    assert human_review.status == AgentStageCheckpointStatus.COMPLETED
    assert human_review.output["gate_satisfied"] is True
    assert workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert superdocs.status == AgentStageCheckpointStatus.WAITING
    assert superdocs.output["pending_start"]
    assert superdocs.token_count is None
    assert ingest.completed_at == ingest_completed_at
    second = db.get(Finding, second_id)
    assert second is not None
    assert second.approval_decision is not None
    assert second.approval_decision.approved is True
