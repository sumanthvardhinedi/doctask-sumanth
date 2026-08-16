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
from app.services.rule_context import retrieve_rule_context
from app.services.rule_indexer import index_all_authorities
from app.services.rule_interpreter import interpret_rules
from app.workflow.agent_workflow import start_or_resume_agent_workflow


def test_retrieve_rule_context_is_authority_scoped() -> None:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            index_all_authorities(db)
            context = retrieve_rule_context(db, "authority_a")
            assert context["retrieval_method"] == "deterministic_metadata"
            assert context["rule_count"] == 8
            assert "mandatory.cover_letter" in context["rule_ids"]
            assert "mandatory.executive_summary" not in context["rule_ids"]
    finally:
        Base.metadata.drop_all(bind=engine)


def test_retrieve_rule_context_focuses_classified_ids_without_dropping_rules() -> None:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            index_all_authorities(db)
            context = retrieve_rule_context(
                db,
                "authority_a",
                classified_rule_ids=["mandatory.cover_letter", "invented.rule"],
            )
            assert context["rule_count"] == 8
            assert context["focused_rule_ids"] == ["mandatory.cover_letter"]
            assert "invented.rule" not in context["rule_ids"]
    finally:
        Base.metadata.drop_all(bind=engine)


def test_interpret_rules_uses_published_text_only() -> None:
    interpretations = interpret_rules(
        authority_code="authority_a",
        rules=[
            {
                "rule_id": "mandatory.cover_letter",
                "description": "Cover letter is required",
                "source_citation": "Authority A Published Filing Rules",
                "parameters": {"filename": "cover_letter.pdf"},
            }
        ],
    )

    assert interpretations[0]["result"] == "interpreted"
    assert interpretations[0]["interpretation"] == "Cover letter is required"
    assert interpretations[0]["parameters"] == {"filename": "cover_letter.pdf"}
    assert interpretations[0]["authority"] == "authority_a"


def test_interpret_rules_missing_description_is_insufficient() -> None:
    interpretations = interpret_rules(
        authority_code="authority_a",
        rules=[{"rule_id": "x", "description": None, "parameters": {}}],
    )

    assert interpretations[0]["result"] == FindingResult.INSUFFICIENT_EVIDENCE
    assert interpretations[0]["interpretation"] is None


def test_interpret_rules_does_not_invent_extra_requirements() -> None:
    interpretations = interpret_rules(
        authority_code="authority_a",
        rules=[
            {
                "rule_id": "x",
                "description": "Cover letter is required",
                "parameters": {"filename": "cover_letter.pdf"},
                "also_require": "a notarized affidavit",
            }
        ],
    )

    assert "affidavit" not in str(interpretations[0]["interpretation"])
    assert interpretations[0]["parameters"] == {"filename": "cover_letter.pdf"}


def test_agent_retrieves_and_interprets_rules() -> None:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)
    try:
        with Session(engine) as db:
            index_all_authorities(db)
            package = FilingPackage(
                id=uuid.uuid4(),
                authority_code="authority_a",
                name="Rule context package",
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
            retrieve = (
                db.query(AgentStageCheckpoint)
                .filter(
                    AgentStageCheckpoint.workflow_id == workflow.id,
                    AgentStageCheckpoint.stage
                    == AgentWorkflowStage.RETRIEVE_RULE_CONTEXT,
                )
                .one()
            )
            interpret = (
                db.query(AgentStageCheckpoint)
                .filter(
                    AgentStageCheckpoint.workflow_id == workflow.id,
                    AgentStageCheckpoint.stage == AgentWorkflowStage.INTERPRET_RULES,
                )
                .one()
            )
            assert retrieve.output["rule_count"] == 8
            assert retrieve.output["focused_rule_ids"] == ["mandatory.cover_letter"]
            assert interpret.output["interpretation_count"] == 8
            assert all(
                item["result"] == "interpreted"
                for item in interpret.output["interpretations"]
            )
            assert retrieve.token_count is None
            assert interpret.token_count is None

            retrieve_completed = retrieve.completed_at
            start_or_resume_agent_workflow(db, package.id)
            db.refresh(retrieve)
            assert retrieve.completed_at == retrieve_completed
    finally:
        Base.metadata.drop_all(bind=engine)
