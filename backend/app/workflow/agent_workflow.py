from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.agent_workflow import AgentStageCheckpoint, AgentWorkflow
from app.models.enums import (
    AgentStageCheckpointStatus,
    AgentWorkflowStage,
    AgentWorkflowStatus,
    FindingResult,
)
from app.models.filing import FilingPackage
from app.models.finding import Finding
from app.models.validation import ValidationRun
from app.services.regulatory_rule_provider import get_indexed_rule_definitions
from app.services.rule_indexer import index_authority_rules
from app.workflow.validation_workflow import run_validation

ALLOWED_WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    AgentWorkflowStatus.PENDING: {AgentWorkflowStatus.RUNNING},
    AgentWorkflowStatus.RUNNING: {
        AgentWorkflowStatus.RUNNING,
        AgentWorkflowStatus.WAITING_FOR_HUMAN,
        AgentWorkflowStatus.COMPLETED,
        AgentWorkflowStatus.FAILED,
    },
    AgentWorkflowStatus.FAILED: {AgentWorkflowStatus.RUNNING},
    AgentWorkflowStatus.WAITING_FOR_HUMAN: set(),
    AgentWorkflowStatus.COMPLETED: set(),
}

_TERMINAL_STATUSES = {
    AgentWorkflowStatus.COMPLETED,
    AgentWorkflowStatus.WAITING_FOR_HUMAN,
}


class AgentGraphState(TypedDict):
    package_id: str
    workflow_id: str
    validation_run_id: str | None
    error: str | None


def apply_workflow_status(
    workflow: AgentWorkflow,
    new_status: AgentWorkflowStatus | str,
) -> None:
    """Apply a legal workflow status transition or raise ValueError."""

    target = str(new_status)
    current = workflow.status
    allowed = ALLOWED_WORKFLOW_TRANSITIONS.get(current, set())

    if target == current:
        return

    if target not in allowed:
        raise ValueError(
            f"Invalid workflow transition: {current} -> {target}"
        )

    workflow.status = target

    now = datetime.now(timezone.utc)
    if target == AgentWorkflowStatus.RUNNING and workflow.started_at is None:
        workflow.started_at = now
    if target in {
        AgentWorkflowStatus.COMPLETED,
        AgentWorkflowStatus.FAILED,
        AgentWorkflowStatus.WAITING_FOR_HUMAN,
    }:
        workflow.completed_at = now


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_workflow(db: Session, workflow_id: uuid.UUID) -> AgentWorkflow:
    workflow = db.get(AgentWorkflow, workflow_id)
    if workflow is None:
        raise ValueError(f"Agent workflow {workflow_id} not found")
    return workflow


def _get_checkpoint(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
) -> AgentStageCheckpoint | None:
    return db.scalar(
        select(AgentStageCheckpoint).where(
            AgentStageCheckpoint.workflow_id == workflow_id,
            AgentStageCheckpoint.stage == stage,
        )
    )


def _stage_completed(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
) -> bool:
    checkpoint = _get_checkpoint(db, workflow_id, stage)
    return (
        checkpoint is not None
        and checkpoint.status == AgentStageCheckpointStatus.COMPLETED
    )


def _begin_stage(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
) -> AgentStageCheckpoint:
    workflow = _get_workflow(db, workflow_id)
    workflow.current_stage = stage
    db.flush()

    checkpoint = _get_checkpoint(db, workflow_id, stage)
    if checkpoint is None:
        checkpoint = AgentStageCheckpoint(
            workflow_id=workflow_id,
            stage=stage,
            started_at=_utcnow(),
        )
        db.add(checkpoint)
        db.flush()
    elif checkpoint.started_at is None:
        checkpoint.started_at = _utcnow()
        db.flush()

    return checkpoint


def _complete_stage(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
    output: dict | None = None,
    *,
    skipped: bool = False,
) -> AgentStageCheckpoint:
    checkpoint = _begin_stage(db, workflow_id, stage)
    checkpoint.status = (
        AgentStageCheckpointStatus.SKIPPED
        if skipped
        else AgentStageCheckpointStatus.COMPLETED
    )
    checkpoint.output = output
    checkpoint.completed_at = _utcnow()
    # No LLM/API tokens in this slice; record unused fields explicitly.
    checkpoint.model_provider = None
    checkpoint.model_operation = None
    checkpoint.token_count = None
    checkpoint.estimated_cost = None
    db.commit()
    return checkpoint


def _fail_stage(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
    error: str,
) -> None:
    checkpoint = _begin_stage(db, workflow_id, stage)
    checkpoint.status = AgentStageCheckpointStatus.FAILED
    checkpoint.output = {"error": error}
    checkpoint.completed_at = _utcnow()
    checkpoint.model_provider = None
    checkpoint.model_operation = None
    checkpoint.token_count = None
    checkpoint.estimated_cost = None

    workflow = _get_workflow(db, workflow_id)
    workflow.error = error
    apply_workflow_status(workflow, AgentWorkflowStatus.FAILED)
    db.commit()


def _latest_workflow_for_package(
    db: Session,
    package_id: uuid.UUID,
) -> AgentWorkflow | None:
    return db.scalar(
        select(AgentWorkflow)
        .where(AgentWorkflow.package_id == package_id)
        .order_by(AgentWorkflow.created_at.desc())
    )


def ingest_package_stage(db: Session, workflow_id: uuid.UUID, package_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.INGEST_PACKAGE):
        checkpoint = _get_checkpoint(db, workflow_id, AgentWorkflowStage.INGEST_PACKAGE)
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.INGEST_PACKAGE)

    package = db.scalar(
        select(FilingPackage)
        .options(selectinload(FilingPackage.documents))
        .where(FilingPackage.id == package_id)
    )

    if package is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.INGEST_PACKAGE,
            f"Filing package {package_id} not found",
        )
        raise ValueError(f"Filing package {package_id} not found")

    output = {
        "package_id": str(package.id),
        "authority_code": package.authority_code,
        "document_ids": [str(document.id) for document in package.documents],
        "document_count": len(package.documents),
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.INGEST_PACKAGE, output)
    return output


def load_authority_rules_stage(db: Session, workflow_id: uuid.UUID, package_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.LOAD_AUTHORITY_RULES):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.LOAD_AUTHORITY_RULES
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.LOAD_AUTHORITY_RULES)

    package = db.get(FilingPackage, package_id)
    if package is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.LOAD_AUTHORITY_RULES,
            f"Filing package {package_id} not found",
        )
        raise ValueError(f"Filing package {package_id} not found")

    try:
        index_authority_rules(package.authority_code, db)
        rules = get_indexed_rule_definitions(db, package.authority_code)
    except Exception as exc:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.LOAD_AUTHORITY_RULES,
            str(exc),
        )
        raise

    output = {
        "authority_code": package.authority_code,
        "rule_ids": [rule.rule_id for rule in rules],
        "rule_count": len(rules),
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.LOAD_AUTHORITY_RULES, output)
    return output


def validate_package_stage(db: Session, workflow_id: uuid.UUID, package_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.VALIDATE_PACKAGE):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.VALIDATE_PACKAGE
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.VALIDATE_PACKAGE)
    workflow = _get_workflow(db, workflow_id)

    if workflow.validation_run_id is not None:
        existing_run = db.get(ValidationRun, workflow.validation_run_id)
        if existing_run is not None:
            output = {
                "validation_run_id": str(existing_run.id),
                "status": existing_run.status,
            }
            _complete_stage(
                db,
                workflow_id,
                AgentWorkflowStage.VALIDATE_PACKAGE,
                output,
                skipped=True,
            )
            return output

    try:
        validation_run = run_validation(db, package_id)
    except Exception as exc:
        workflow = _get_workflow(db, workflow_id)
        failed_run = db.scalar(
            select(ValidationRun)
            .where(ValidationRun.package_id == package_id)
            .order_by(ValidationRun.created_at.desc())
        )
        if failed_run is not None:
            workflow.validation_run_id = failed_run.id
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.VALIDATE_PACKAGE,
            str(exc),
        )
        raise

    workflow = _get_workflow(db, workflow_id)
    workflow.validation_run_id = validation_run.id
    output = {
        "validation_run_id": str(validation_run.id),
        "status": validation_run.status,
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.VALIDATE_PACKAGE, output)
    return output


def generate_findings_stage(db: Session, workflow_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS)
    workflow = _get_workflow(db, workflow_id)

    if workflow.validation_run_id is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.GENERATE_FINDINGS,
            "Validation run is missing; cannot generate findings",
        )
        raise ValueError("Validation run is missing; cannot generate findings")

    findings = (
        db.query(Finding)
        .filter(Finding.validation_run_id == workflow.validation_run_id)
        .all()
    )
    output = {
        "validation_run_id": str(workflow.validation_run_id),
        "finding_count": len(findings),
        "finding_ids": [str(finding.id) for finding in findings],
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS, output)
    return output


def human_review_stage(db: Session, workflow_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW):
        checkpoint = _get_checkpoint(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW)
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW)
    workflow = _get_workflow(db, workflow_id)

    if workflow.validation_run_id is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.HUMAN_REVIEW,
            "Validation run is missing; cannot route human review",
        )
        raise ValueError("Validation run is missing; cannot route human review")

    findings = (
        db.query(Finding)
        .filter(Finding.validation_run_id == workflow.validation_run_id)
        .all()
    )
    requires_review = any(
        finding.result
        in (
            FindingResult.FAIL,
            FindingResult.INSUFFICIENT_EVIDENCE,
        )
        for finding in findings
    )

    if requires_review:
        apply_workflow_status(workflow, AgentWorkflowStatus.WAITING_FOR_HUMAN)
        output = {
            "requires_review": True,
            "status": AgentWorkflowStatus.WAITING_FOR_HUMAN,
        }
    else:
        apply_workflow_status(workflow, AgentWorkflowStatus.COMPLETED)
        output = {
            "requires_review": False,
            "status": AgentWorkflowStatus.COMPLETED,
        }

    _complete_stage(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW, output)
    return output


def _build_graph(db: Session):
    def ingest(state: AgentGraphState) -> AgentGraphState:
        ingest_package_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return state

    def load_rules(state: AgentGraphState) -> AgentGraphState:
        load_authority_rules_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return state

    def validate(state: AgentGraphState) -> AgentGraphState:
        output = validate_package_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return {
            **state,
            "validation_run_id": output.get("validation_run_id"),
        }

    def findings(state: AgentGraphState) -> AgentGraphState:
        generate_findings_stage(db, uuid.UUID(state["workflow_id"]))
        return state

    def human_review(state: AgentGraphState) -> AgentGraphState:
        human_review_stage(db, uuid.UUID(state["workflow_id"]))
        return state

    graph = StateGraph(AgentGraphState)
    graph.add_node(AgentWorkflowStage.INGEST_PACKAGE, ingest)
    graph.add_node(AgentWorkflowStage.LOAD_AUTHORITY_RULES, load_rules)
    graph.add_node(AgentWorkflowStage.VALIDATE_PACKAGE, validate)
    graph.add_node(AgentWorkflowStage.GENERATE_FINDINGS, findings)
    graph.add_node(AgentWorkflowStage.HUMAN_REVIEW, human_review)
    graph.add_edge(START, AgentWorkflowStage.INGEST_PACKAGE)
    graph.add_edge(AgentWorkflowStage.INGEST_PACKAGE, AgentWorkflowStage.LOAD_AUTHORITY_RULES)
    graph.add_edge(AgentWorkflowStage.LOAD_AUTHORITY_RULES, AgentWorkflowStage.VALIDATE_PACKAGE)
    graph.add_edge(AgentWorkflowStage.VALIDATE_PACKAGE, AgentWorkflowStage.GENERATE_FINDINGS)
    graph.add_edge(AgentWorkflowStage.GENERATE_FINDINGS, AgentWorkflowStage.HUMAN_REVIEW)
    graph.add_edge(AgentWorkflowStage.HUMAN_REVIEW, END)
    return graph.compile()


def start_or_resume_agent_workflow(
    db: Session,
    package_id: uuid.UUID,
) -> ValidationRun:
    """Start or resume the durable agent workflow for a filing package."""

    package = db.get(FilingPackage, package_id)
    if package is None:
        raise ValueError(f"Filing package {package_id} not found")

    workflow = _latest_workflow_for_package(db, package_id)

    if workflow is not None and workflow.status in _TERMINAL_STATUSES:
        if workflow.validation_run_id is None:
            raise ValueError("Completed agent workflow is missing a validation run")
        validation_run = db.get(ValidationRun, workflow.validation_run_id)
        if validation_run is None:
            raise ValueError("Completed agent workflow validation run was not found")
        return validation_run

    if workflow is None:
        workflow = AgentWorkflow(
            package_id=package.id,
            authority_code=package.authority_code,
            status=AgentWorkflowStatus.PENDING,
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

    if workflow.status == AgentWorkflowStatus.FAILED:
        workflow.retry_count += 1
        workflow.error = None

    apply_workflow_status(workflow, AgentWorkflowStatus.RUNNING)
    db.commit()

    compiled = _build_graph(db)
    compiled.invoke(
        {
            "package_id": str(package_id),
            "workflow_id": str(workflow.id),
            "validation_run_id": (
                str(workflow.validation_run_id)
                if workflow.validation_run_id
                else None
            ),
            "error": None,
        }
    )

    workflow = _get_workflow(db, workflow.id)
    if workflow.validation_run_id is None:
        raise ValueError("Agent workflow finished without a validation run")

    validation_run = db.get(ValidationRun, workflow.validation_run_id)
    if validation_run is None:
        raise ValueError("Agent workflow validation run was not found")
    return validation_run
