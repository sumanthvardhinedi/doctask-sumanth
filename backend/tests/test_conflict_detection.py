import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.models import (
    AgentStageCheckpoint,
    AgentWorkflow,
    AgentWorkflowStage,
    FilingPackage,
    FindingResult,
    PackageDocument,
    PackageStatus,
)
from app.services.conflict_detector import (
    ROUTE_CONTINUE,
    ROUTE_FINDING,
    ROUTE_HUMAN_ESCALATION,
    ROUTE_HUMAN_REVIEW,
    detect_conflicts,
)
from app.services.rule_indexer import index_all_authorities
from app.workflow.agent_workflow import start_or_resume_agent_workflow


def test_signature_requirement_without_extraction_is_conflict() -> None:
    result = detect_conflicts(
        rules=[
            {
                "rule_id": "signature.cover_letter",
                "rule_type": "requires_signature",
                "parameters": {"filename": "cover_letter.pdf"},
            }
        ],
        interpretations=[
            {"rule_id": "signature.cover_letter", "result": "interpreted"}
        ],
        extracted_documents=[
            {
                "filename": "cover_letter.pdf",
                "signature": {
                    "result": FindingResult.INSUFFICIENT_EVIDENCE,
                    "value": None,
                },
            }
        ],
        findings=[
            {
                "rule_id": "signature.cover_letter",
                "result": FindingResult.INSUFFICIENT_EVIDENCE,
            }
        ],
    )

    assert result["conflict_count"] == 1
    assert result["routes"][0]["route"] == ROUTE_HUMAN_REVIEW
    assert result["requires_human_review"] is True


def test_missing_document_fail_is_finding_not_conflict() -> None:
    result = detect_conflicts(
        rules=[
            {
                "rule_id": "signature.cover_letter",
                "rule_type": "requires_signature",
                "parameters": {"filename": "cover_letter.pdf"},
            }
        ],
        interpretations=[
            {"rule_id": "signature.cover_letter", "result": "interpreted"}
        ],
        extracted_documents=[],
        findings=[
            {"rule_id": "signature.cover_letter", "result": FindingResult.FAIL}
        ],
    )

    assert result["conflict_count"] == 0
    assert result["routes"][0]["route"] == ROUTE_FINDING


def test_pass_without_extraction_evidence_is_conflict() -> None:
    result = detect_conflicts(
        rules=[
            {
                "rule_id": "signature.cover_letter",
                "rule_type": "requires_signature",
                "parameters": {"filename": "cover_letter.pdf"},
            }
        ],
        interpretations=[
            {"rule_id": "signature.cover_letter", "result": "interpreted"}
        ],
        extracted_documents=[
            {
                "filename": "cover_letter.pdf",
                "signature": {
                    "result": FindingResult.INSUFFICIENT_EVIDENCE,
                    "value": None,
                },
            }
        ],
        findings=[
            {"rule_id": "signature.cover_letter", "result": FindingResult.PASS}
        ],
    )

    assert result["conflict_count"] == 1
    assert result["routes"][0]["route"] == ROUTE_HUMAN_REVIEW


def test_pass_with_observed_evidence_continues() -> None:
    result = detect_conflicts(
        rules=[
            {
                "rule_id": "signature.cover_letter",
                "rule_type": "requires_signature",
                "parameters": {"filename": "cover_letter.pdf"},
            }
        ],
        interpretations=[
            {"rule_id": "signature.cover_letter", "result": "interpreted"}
        ],
        extracted_documents=[
            {
                "filename": "cover_letter.pdf",
                "signature": {"result": "observed", "value": True},
            }
        ],
        findings=[
            {"rule_id": "signature.cover_letter", "result": FindingResult.PASS}
        ],
    )

    assert result["conflict_count"] == 0
    assert result["routes"][0]["route"] == ROUTE_CONTINUE


def test_insufficient_format_rule_escalates_without_inventing_conflict() -> None:
    result = detect_conflicts(
        rules=[
            {
                "rule_id": "format.pdf_only",
                "rule_type": "allowed_content_types",
                "parameters": {"content_types": ["application/pdf"]},
            }
        ],
        interpretations=[{"rule_id": "format.pdf_only", "result": "interpreted"}],
        extracted_documents=[],
        findings=[
            {
                "rule_id": "format.pdf_only",
                "result": FindingResult.INSUFFICIENT_EVIDENCE,
            }
        ],
    )

    assert result["conflict_count"] == 0
    assert result["routes"][0]["route"] == ROUTE_HUMAN_ESCALATION


def test_agent_detects_signature_conflict_and_skips_on_resume() -> None:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            index_all_authorities(db)
            package = FilingPackage(
                id=uuid.uuid4(),
                authority_code="authority_a",
                name="Conflict package",
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

            start_or_resume_agent_workflow(db, package.id)
            workflow = (
                db.query(AgentWorkflow)
                .filter(AgentWorkflow.package_id == package.id)
                .one()
            )
            checkpoint = (
                db.query(AgentStageCheckpoint)
                .filter(
                    AgentStageCheckpoint.workflow_id == workflow.id,
                    AgentStageCheckpoint.stage == AgentWorkflowStage.DETECT_CONFLICTS,
                )
                .one()
            )
            conflict_ids = {
                item["rule_id"] for item in checkpoint.output["conflicts"]
            }
            assert "signature.cover_letter" in conflict_ids
            assert "declaration.cover_letter" in conflict_ids
            assert checkpoint.output["requires_human_review"] is True
            assert checkpoint.token_count is None
            completed_at = checkpoint.completed_at

            start_or_resume_agent_workflow(db, package.id)
            db.refresh(checkpoint)
            assert checkpoint.completed_at == completed_at
    finally:
        Base.metadata.drop_all(bind=engine)
