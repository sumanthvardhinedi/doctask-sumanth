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
    PackageStatus,
    SuperDocsReviewStatus,
)
from app.models.filing import FilingPackage
from app.models.finding import Finding
from app.models.superdocs_review import SuperDocsReviewSession
from app.models.validation import ValidationRun
from app.services.conflict_detector import detect_conflicts as detect_requirement_conflicts
from app.services.human_review_gate import (
    evaluate_human_review_gate,
    finding_gate_item,
)
from app.services.superdocs_loop import (
    evaluate_superdocs_loop,
    is_unreadable_document_error,
)
from app.integrations.superdocs.client import SuperDocsClient
from app.storage.document_store import DocumentStore
from app.workflow.superdocs_review import (
    SuperDocsReviewAlreadyExists,
    SuperDocsReviewError,
    export_superdocs_review,
    start_superdocs_review,
)
from app.services.document_classifier import classify_documents
from app.services.rule_context import retrieve_rule_context as build_rule_context
from app.services.rule_interpreter import interpret_rules as interpret_published_rules
from app.services.structure_extractor import extract_structure
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
    AgentWorkflowStatus.WAITING_FOR_HUMAN: {AgentWorkflowStatus.RUNNING},
    AgentWorkflowStatus.COMPLETED: set(),
}

_TERMINAL_STATUSES = {
    AgentWorkflowStatus.COMPLETED,
}


class AgentGraphState(TypedDict):
    package_id: str
    workflow_id: str
    validation_run_id: str | None
    error: str | None
    halt: bool


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
    if target == AgentWorkflowStatus.RUNNING:
        if workflow.started_at is None:
            workflow.started_at = now
        if current == AgentWorkflowStatus.WAITING_FOR_HUMAN:
            workflow.completed_at = None
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


def classify_documents_stage(db: Session, workflow_id: uuid.UUID, package_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.CLASSIFY_DOCUMENTS):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.CLASSIFY_DOCUMENTS
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.CLASSIFY_DOCUMENTS)

    package = db.scalar(
        select(FilingPackage)
        .options(selectinload(FilingPackage.documents))
        .where(FilingPackage.id == package_id)
    )

    if package is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.CLASSIFY_DOCUMENTS,
            f"Filing package {package_id} not found",
        )
        raise ValueError(f"Filing package {package_id} not found")

    documents = [
        {
            "id": str(document.id),
            "filename": document.filename,
            "content_type": document.content_type,
            "sort_order": document.sort_order,
        }
        for document in sorted(package.documents, key=lambda item: item.sort_order)
    ]

    try:
        classifications = classify_documents(
            authority_code=package.authority_code,
            documents=documents,
        )
    except Exception as exc:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.CLASSIFY_DOCUMENTS,
            str(exc),
        )
        raise

    output = {
        "authority_code": package.authority_code,
        "document_count": len(classifications),
        "classifications": classifications,
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.CLASSIFY_DOCUMENTS, output)
    return output


def extract_structure_stage(db: Session, workflow_id: uuid.UUID, package_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE)

    package = db.scalar(
        select(FilingPackage)
        .options(selectinload(FilingPackage.documents))
        .where(FilingPackage.id == package_id)
    )

    if package is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.EXTRACT_STRUCTURE,
            f"Filing package {package_id} not found",
        )
        raise ValueError(f"Filing package {package_id} not found")

    documents = [
        {
            "id": str(document.id),
            "filename": document.filename,
            "content_type": document.content_type,
            "file_size_bytes": document.file_size_bytes,
            "sort_order": document.sort_order,
        }
        for document in package.documents
    ]

    output = extract_structure(documents=documents)
    _complete_stage(db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE, output)
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


def retrieve_rule_context_stage(
    db: Session,
    workflow_id: uuid.UUID,
    package_id: uuid.UUID,
) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT)

    package = db.get(FilingPackage, package_id)
    if package is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.RETRIEVE_RULE_CONTEXT,
            f"Filing package {package_id} not found",
        )
        raise ValueError(f"Filing package {package_id} not found")

    classify_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.CLASSIFY_DOCUMENTS
    )
    classified_rule_ids: list[str] = []
    if classify_checkpoint and classify_checkpoint.output:
        for item in classify_checkpoint.output.get("classifications") or []:
            rule_id = item.get("rule_id")
            if rule_id:
                classified_rule_ids.append(str(rule_id))

    try:
        output = build_rule_context(
            db,
            package.authority_code,
            classified_rule_ids=classified_rule_ids,
        )
    except Exception as exc:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.RETRIEVE_RULE_CONTEXT,
            str(exc),
        )
        raise

    _complete_stage(db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT, output)
    return output


def interpret_rules_stage(db: Session, workflow_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.INTERPRET_RULES):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.INTERPRET_RULES
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.INTERPRET_RULES)

    context_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT
    )
    if context_checkpoint is None or not context_checkpoint.output:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.INTERPRET_RULES,
            "Rule context is missing; cannot interpret rules",
        )
        raise ValueError("Rule context is missing; cannot interpret rules")

    authority_code = str(context_checkpoint.output.get("authority_code") or "")
    rules = list(context_checkpoint.output.get("rules") or [])
    interpretations = interpret_published_rules(
        authority_code=authority_code,
        rules=rules,
    )
    output = {
        "authority_code": authority_code,
        "interpretation_count": len(interpretations),
        "interpretations": interpretations,
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.INTERPRET_RULES, output)
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
        extract_checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE
        )
        extracted_structure = (
            extract_checkpoint.output if extract_checkpoint is not None else None
        )
        validation_run = run_validation(
            db,
            package_id,
            extracted_structure=extracted_structure,
        )
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
    interpret_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.INTERPRET_RULES
    )
    interpretations = []
    if interpret_checkpoint and interpret_checkpoint.output:
        interpretations = list(
            interpret_checkpoint.output.get("interpretations") or []
        )
    citation_by_rule = {
        item.get("rule_id"): item.get("source_citation")
        for item in interpretations
        if item.get("rule_id")
    }
    output = {
        "validation_run_id": str(workflow.validation_run_id),
        "finding_count": len(findings),
        "finding_ids": [str(finding.id) for finding in findings],
        "finding_results": [
            {
                "rule_id": finding.rule_id,
                "result": finding.result,
                "source_citation": citation_by_rule.get(finding.rule_id),
            }
            for finding in findings
        ],
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS, output)
    return output


def detect_conflicts_stage(db: Session, workflow_id: uuid.UUID) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.DETECT_CONFLICTS):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.DETECT_CONFLICTS
        )
        return checkpoint.output or {}

    _begin_stage(db, workflow_id, AgentWorkflowStage.DETECT_CONFLICTS)

    retrieve_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT
    )
    interpret_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.INTERPRET_RULES
    )
    extract_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.EXTRACT_STRUCTURE
    )
    findings_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.GENERATE_FINDINGS
    )

    rules = []
    if retrieve_checkpoint and retrieve_checkpoint.output:
        rules = list(retrieve_checkpoint.output.get("rules") or [])
    interpretations = []
    if interpret_checkpoint and interpret_checkpoint.output:
        interpretations = list(
            interpret_checkpoint.output.get("interpretations") or []
        )
    extracted_documents = []
    if extract_checkpoint and extract_checkpoint.output:
        extracted_documents = list(
            extract_checkpoint.output.get("documents") or []
        )
    findings = []
    if findings_checkpoint and findings_checkpoint.output:
        findings = list(findings_checkpoint.output.get("finding_results") or [])

    output = detect_requirement_conflicts(
        rules=rules,
        interpretations=interpretations,
        extracted_documents=extracted_documents,
        findings=findings,
    )
    _complete_stage(db, workflow_id, AgentWorkflowStage.DETECT_CONFLICTS, output)
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

    findings = db.scalars(
        select(Finding)
        .where(Finding.validation_run_id == workflow.validation_run_id)
        .options(selectinload(Finding.approval_decision))
        .order_by(Finding.created_at.asc())
    ).all()
    conflict_checkpoint = _get_checkpoint(
        db, workflow_id, AgentWorkflowStage.DETECT_CONFLICTS
    )
    conflict_rule_ids: list[str] = []
    requires_review = any(
        finding.result
        in (
            FindingResult.FAIL,
            FindingResult.INSUFFICIENT_EVIDENCE,
        )
        for finding in findings
    )
    if conflict_checkpoint and conflict_checkpoint.output:
        requires_review = requires_review or bool(
            conflict_checkpoint.output.get("requires_human_review")
        )
        conflict_rule_ids = [
            str(item.get("rule_id"))
            for item in list(conflict_checkpoint.output.get("conflicts") or [])
            if item.get("rule_id")
        ]

    gate = evaluate_human_review_gate(
        findings=[finding_gate_item(finding) for finding in findings],
        conflict_rule_ids=conflict_rule_ids,
    )

    if requires_review and not gate["gate_satisfied"]:
        output = {
            **gate,
            "requires_review": True,
            "status": AgentWorkflowStatus.WAITING_FOR_HUMAN,
            "gate_satisfied": False,
        }
        _park_stage(
            db,
            workflow_id,
            AgentWorkflowStage.HUMAN_REVIEW,
            output,
        )
        return output

    output = {
        **gate,
        "requires_review": bool(requires_review),
        "status": AgentWorkflowStatus.RUNNING,
        "gate_satisfied": True,
    }
    _complete_stage(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW, output)
    return output


def _park_stage(
    db: Session,
    workflow_id: uuid.UUID,
    stage: AgentWorkflowStage,
    output: dict,
) -> AgentStageCheckpoint:
    checkpoint = _begin_stage(db, workflow_id, stage)
    checkpoint.status = AgentStageCheckpointStatus.WAITING
    checkpoint.output = output
    checkpoint.completed_at = None
    checkpoint.model_provider = None
    checkpoint.model_operation = None
    checkpoint.token_count = None
    checkpoint.estimated_cost = None
    workflow = _get_workflow(db, workflow_id)
    apply_workflow_status(workflow, AgentWorkflowStatus.WAITING_FOR_HUMAN)
    db.commit()
    return checkpoint


def _load_findings_for_run(db: Session, validation_run_id: uuid.UUID) -> list[Finding]:
    return list(
        db.scalars(
            select(Finding)
            .where(Finding.validation_run_id == validation_run_id)
            .options(selectinload(Finding.approval_decision))
            .order_by(Finding.created_at.asc())
        ).all()
    )


def superdocs_review_stage(
    db: Session,
    workflow_id: uuid.UUID,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.SUPERDOCS_REVIEW):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.SUPERDOCS_REVIEW
        )
        return checkpoint.output or {}

    if not _stage_completed(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW):
        raise ValueError("Human review gate is unmet; SuperDocs must not run")

    _begin_stage(db, workflow_id, AgentWorkflowStage.SUPERDOCS_REVIEW)
    workflow = _get_workflow(db, workflow_id)
    if workflow.validation_run_id is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.SUPERDOCS_REVIEW,
            "Validation run is missing; cannot start SuperDocs review",
        )
        raise ValueError("Validation run is missing; cannot start SuperDocs review")

    findings = _load_findings_for_run(db, workflow.validation_run_id)
    reviews = list(
        db.scalars(
            select(SuperDocsReviewSession).where(
                SuperDocsReviewSession.validation_run_id == workflow.validation_run_id
            )
        ).all()
    )
    loop = evaluate_superdocs_loop(findings=findings, reviews=reviews)
    skipped_unreadable: list[dict[str, str]] = []

    if superdocs_client is not None and document_store is not None:
        start_ids = list(loop["pending_start"]) + list(loop["pending_retry"])
        for finding_id in start_ids:
            try:
                start_superdocs_review(
                    db,
                    package_id=workflow.package_id,
                    validation_run_id=workflow.validation_run_id,
                    finding_id=uuid.UUID(str(finding_id)),
                    client=superdocs_client,
                    document_store=document_store,
                )
            except SuperDocsReviewAlreadyExists:
                continue
            except SuperDocsReviewError as exc:
                message = str(exc)
                if is_unreadable_document_error(message):
                    skipped_unreadable.append(
                        {
                            "finding_id": str(finding_id),
                            "reason": "unreadable_document",
                            "evidence": message,
                        }
                    )
                    continue
                raise

        findings = _load_findings_for_run(db, workflow.validation_run_id)
        reviews = list(
            db.scalars(
                select(SuperDocsReviewSession).where(
                    SuperDocsReviewSession.validation_run_id
                    == workflow.validation_run_id
                )
            ).all()
        )
        loop = evaluate_superdocs_loop(findings=findings, reviews=reviews)

    skipped = list(loop["skipped"]) + skipped_unreadable
    pending_start = [
        finding_id
        for finding_id in list(loop["pending_start"])
        if finding_id not in {item["finding_id"] for item in skipped_unreadable}
    ]
    pending_retry = [
        finding_id
        for finding_id in list(loop["pending_retry"])
        if finding_id not in {item["finding_id"] for item in skipped_unreadable}
    ]
    waiting = bool(
        pending_start or loop["pending_decision"] or pending_retry
    )
    output = {
        **loop,
        "skipped": skipped,
        "pending_start": pending_start,
        "pending_retry": pending_retry,
        "loop_waiting": waiting,
        "ready_to_finalize": not waiting,
        "token_count": None,
    }

    if waiting:
        output["status"] = AgentWorkflowStatus.WAITING_FOR_HUMAN
        _park_stage(
            db,
            workflow_id,
            AgentWorkflowStage.SUPERDOCS_REVIEW,
            output,
        )
        return output

    output["status"] = AgentWorkflowStatus.RUNNING
    _complete_stage(db, workflow_id, AgentWorkflowStage.SUPERDOCS_REVIEW, output)
    return output


def finalize_export_stage(
    db: Session,
    workflow_id: uuid.UUID,
    *,
    superdocs_client: SuperDocsClient | None = None,
) -> dict:
    if _stage_completed(db, workflow_id, AgentWorkflowStage.FINALIZE_EXPORT):
        checkpoint = _get_checkpoint(
            db, workflow_id, AgentWorkflowStage.FINALIZE_EXPORT
        )
        return checkpoint.output or {}

    if not _stage_completed(db, workflow_id, AgentWorkflowStage.HUMAN_REVIEW):
        raise ValueError("Human review gate is unmet; export must not run")
    if not _stage_completed(db, workflow_id, AgentWorkflowStage.SUPERDOCS_REVIEW):
        raise ValueError("SuperDocs loop is unmet; export must not run")

    _begin_stage(db, workflow_id, AgentWorkflowStage.FINALIZE_EXPORT)
    workflow = _get_workflow(db, workflow_id)
    if workflow.validation_run_id is None:
        _fail_stage(
            db,
            workflow_id,
            AgentWorkflowStage.FINALIZE_EXPORT,
            "Validation run is missing; cannot finalize export",
        )
        raise ValueError("Validation run is missing; cannot finalize export")

    reviews = list(
        db.scalars(
            select(SuperDocsReviewSession).where(
                SuperDocsReviewSession.validation_run_id == workflow.validation_run_id
            )
        ).all()
    )
    exported_ids: list[str] = []
    skipped_rejected: list[str] = []
    pending_export: list[str] = []

    for review in reviews:
        if review.status == SuperDocsReviewStatus.REJECTED:
            skipped_rejected.append(str(review.id))
            continue
        if review.status == SuperDocsReviewStatus.EXPORTED:
            exported_ids.append(str(review.id))
            continue
        if review.status != SuperDocsReviewStatus.APPROVED:
            continue
        if superdocs_client is None:
            pending_export.append(str(review.id))
            continue
        exported = export_superdocs_review(
            db,
            package_id=workflow.package_id,
            review_id=review.id,
            client=superdocs_client,
        )
        exported_ids.append(str(exported.id))

    output = {
        "exported_review_ids": exported_ids,
        "skipped_rejected_review_ids": skipped_rejected,
        "pending_export_review_ids": pending_export,
        "token_count": None,
    }

    if pending_export:
        output["status"] = AgentWorkflowStatus.WAITING_FOR_HUMAN
        output["gate_unmet"] = True
        _park_stage(
            db,
            workflow_id,
            AgentWorkflowStage.FINALIZE_EXPORT,
            output,
        )
        return output

    package = db.get(FilingPackage, workflow.package_id)
    if package is not None:
        package.status = PackageStatus.COMPLETED
    apply_workflow_status(workflow, AgentWorkflowStatus.COMPLETED)
    output["status"] = AgentWorkflowStatus.COMPLETED
    _complete_stage(db, workflow_id, AgentWorkflowStage.FINALIZE_EXPORT, output)
    return output


def resume_agent_after_human_decision(
    db: Session,
    package_id: uuid.UUID,
    validation_run_id: uuid.UUID,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
) -> None:
    """Re-enter the agent after a per-finding or SuperDocs decision."""

    workflow = _latest_workflow_for_package(db, package_id)
    if workflow is None:
        return
    if workflow.status != AgentWorkflowStatus.WAITING_FOR_HUMAN:
        return
    if workflow.validation_run_id != validation_run_id:
        return
    start_or_resume_agent_workflow(
        db,
        package_id,
        superdocs_client=superdocs_client,
        document_store=document_store,
    )


def _route_if_waiting(waiting_target: str):
    def _route(state: AgentGraphState) -> str:
        if state.get("halt"):
            return END
        return waiting_target

    return _route


def _build_graph(
    db: Session,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
):
    def ingest(state: AgentGraphState) -> AgentGraphState:
        ingest_package_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return state

    def classify(state: AgentGraphState) -> AgentGraphState:
        classify_documents_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return state

    def extract(state: AgentGraphState) -> AgentGraphState:
        extract_structure_stage(
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

    def retrieve_context(state: AgentGraphState) -> AgentGraphState:
        retrieve_rule_context_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            uuid.UUID(state["package_id"]),
        )
        return state

    def interpret(state: AgentGraphState) -> AgentGraphState:
        interpret_rules_stage(db, uuid.UUID(state["workflow_id"]))
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

    def conflicts(state: AgentGraphState) -> AgentGraphState:
        detect_conflicts_stage(db, uuid.UUID(state["workflow_id"]))
        return state

    def human_review(state: AgentGraphState) -> AgentGraphState:
        output = human_review_stage(db, uuid.UUID(state["workflow_id"]))
        return {
            **state,
            "halt": output.get("status") == AgentWorkflowStatus.WAITING_FOR_HUMAN,
        }

    def superdocs(state: AgentGraphState) -> AgentGraphState:
        output = superdocs_review_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            superdocs_client=superdocs_client,
            document_store=document_store,
        )
        return {
            **state,
            "halt": output.get("status") == AgentWorkflowStatus.WAITING_FOR_HUMAN,
        }

    def finalize(state: AgentGraphState) -> AgentGraphState:
        output = finalize_export_stage(
            db,
            uuid.UUID(state["workflow_id"]),
            superdocs_client=superdocs_client,
        )
        return {
            **state,
            "halt": output.get("status") == AgentWorkflowStatus.WAITING_FOR_HUMAN,
        }

    graph = StateGraph(AgentGraphState)
    graph.add_node(AgentWorkflowStage.INGEST_PACKAGE, ingest)
    graph.add_node(AgentWorkflowStage.CLASSIFY_DOCUMENTS, classify)
    graph.add_node(AgentWorkflowStage.EXTRACT_STRUCTURE, extract)
    graph.add_node(AgentWorkflowStage.LOAD_AUTHORITY_RULES, load_rules)
    graph.add_node(AgentWorkflowStage.RETRIEVE_RULE_CONTEXT, retrieve_context)
    graph.add_node(AgentWorkflowStage.INTERPRET_RULES, interpret)
    graph.add_node(AgentWorkflowStage.VALIDATE_PACKAGE, validate)
    graph.add_node(AgentWorkflowStage.GENERATE_FINDINGS, findings)
    graph.add_node(AgentWorkflowStage.DETECT_CONFLICTS, conflicts)
    graph.add_node(AgentWorkflowStage.HUMAN_REVIEW, human_review)
    graph.add_node(AgentWorkflowStage.SUPERDOCS_REVIEW, superdocs)
    graph.add_node(AgentWorkflowStage.FINALIZE_EXPORT, finalize)
    graph.add_edge(START, AgentWorkflowStage.INGEST_PACKAGE)
    graph.add_edge(AgentWorkflowStage.INGEST_PACKAGE, AgentWorkflowStage.CLASSIFY_DOCUMENTS)
    graph.add_edge(AgentWorkflowStage.CLASSIFY_DOCUMENTS, AgentWorkflowStage.EXTRACT_STRUCTURE)
    graph.add_edge(AgentWorkflowStage.EXTRACT_STRUCTURE, AgentWorkflowStage.LOAD_AUTHORITY_RULES)
    graph.add_edge(AgentWorkflowStage.LOAD_AUTHORITY_RULES, AgentWorkflowStage.RETRIEVE_RULE_CONTEXT)
    graph.add_edge(AgentWorkflowStage.RETRIEVE_RULE_CONTEXT, AgentWorkflowStage.INTERPRET_RULES)
    graph.add_edge(AgentWorkflowStage.INTERPRET_RULES, AgentWorkflowStage.VALIDATE_PACKAGE)
    graph.add_edge(AgentWorkflowStage.VALIDATE_PACKAGE, AgentWorkflowStage.GENERATE_FINDINGS)
    graph.add_edge(AgentWorkflowStage.GENERATE_FINDINGS, AgentWorkflowStage.DETECT_CONFLICTS)
    graph.add_edge(AgentWorkflowStage.DETECT_CONFLICTS, AgentWorkflowStage.HUMAN_REVIEW)
    graph.add_conditional_edges(
        AgentWorkflowStage.HUMAN_REVIEW,
        _route_if_waiting(AgentWorkflowStage.SUPERDOCS_REVIEW),
        {
            AgentWorkflowStage.SUPERDOCS_REVIEW: AgentWorkflowStage.SUPERDOCS_REVIEW,
            END: END,
        },
    )
    graph.add_conditional_edges(
        AgentWorkflowStage.SUPERDOCS_REVIEW,
        _route_if_waiting(AgentWorkflowStage.FINALIZE_EXPORT),
        {
            AgentWorkflowStage.FINALIZE_EXPORT: AgentWorkflowStage.FINALIZE_EXPORT,
            END: END,
        },
    )
    graph.add_edge(AgentWorkflowStage.FINALIZE_EXPORT, END)
    return graph.compile()


def start_or_resume_agent_workflow(
    db: Session,
    package_id: uuid.UUID,
    *,
    superdocs_client: SuperDocsClient | None = None,
    document_store: DocumentStore | None = None,
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

    compiled = _build_graph(
        db,
        superdocs_client=superdocs_client,
        document_store=document_store,
    )
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
            "halt": False,
        }
    )

    workflow = _get_workflow(db, workflow.id)
    if workflow.validation_run_id is None:
        raise ValueError("Agent workflow finished without a validation run")

    validation_run = db.get(ValidationRun, workflow.validation_run_id)
    if validation_run is None:
        raise ValueError("Agent workflow validation run was not found")
    return validation_run
