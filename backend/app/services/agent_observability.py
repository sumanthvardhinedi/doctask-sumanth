from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent_workflow import AgentStageCheckpoint, AgentWorkflow
from app.models.enums import (
    AgentStageCheckpointStatus,
    AgentWorkflowStatus,
    SuperDocsReviewStatus,
)
from app.models.superdocs_review import SuperDocsReviewSession


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def duration_ms(started_at: datetime | None, ended_at: datetime | None) -> int | None:
    """Elapsed milliseconds between two timestamps, or None if either is missing."""

    start = _aware(started_at)
    end = _aware(ended_at)
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _sum_optional_ints(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _sum_optional_floats(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present))


def _checkpoint_error(checkpoint: AgentStageCheckpoint) -> str | None:
    if checkpoint.status != AgentStageCheckpointStatus.FAILED:
        return None
    output = checkpoint.output or {}
    error = output.get("error")
    if error is None:
        return None
    return str(error)


def _superdocs_api_operations(
    db: Session,
    validation_run_id: uuid.UUID | None,
) -> list[dict[str, str | int]]:
    if validation_run_id is None:
        return []

    reviews = list(
        db.scalars(
            select(SuperDocsReviewSession).where(
                SuperDocsReviewSession.validation_run_id == validation_run_id
            )
        ).all()
    )
    if not reviews:
        return []

    operations: list[dict[str, str | int]] = [
        {
            "provider": "superdocs",
            "operation": "session",
            "count": len(reviews),
        }
    ]
    exported = sum(
        1 for review in reviews if review.status == SuperDocsReviewStatus.EXPORTED
    )
    if exported:
        operations.append(
            {
                "provider": "superdocs",
                "operation": "export",
                "count": exported,
            }
        )
    return operations


def build_agent_observability(
    db: Session,
    workflow: AgentWorkflow,
    *,
    now: datetime | None = None,
) -> dict:
    """Machine-readable snapshot of stage status, timing, retries, and honest cost."""

    observed_at = _aware(now) or datetime.now(timezone.utc)
    checkpoints = list(
        db.scalars(
            select(AgentStageCheckpoint)
            .where(AgentStageCheckpoint.workflow_id == workflow.id)
            .order_by(
                AgentStageCheckpoint.started_at.asc().nulls_last(),
                AgentStageCheckpoint.created_at.asc(),
            )
        ).all()
    )

    stages: list[dict] = []
    for checkpoint in checkpoints:
        started_at = _aware(checkpoint.started_at)
        completed_at = _aware(checkpoint.completed_at)
        stages.append(
            {
                "stage": checkpoint.stage,
                "status": checkpoint.status,
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_ms": duration_ms(started_at, completed_at),
                "elapsed_ms": duration_ms(started_at, completed_at or observed_at),
                "error": _checkpoint_error(checkpoint),
                "model_provider": checkpoint.model_provider,
                "model_operation": checkpoint.model_operation,
                "token_count": checkpoint.token_count,
                "estimated_cost": checkpoint.estimated_cost,
            }
        )

    started_at = _aware(workflow.started_at)
    completed_at = _aware(workflow.completed_at)
    run_finished = workflow.status in {
        AgentWorkflowStatus.COMPLETED,
        AgentWorkflowStatus.FAILED,
    }
    total_duration_ms = (
        duration_ms(started_at, completed_at) if run_finished else None
    )

    return {
        "id": workflow.id,
        "package_id": workflow.package_id,
        "validation_run_id": workflow.validation_run_id,
        "status": workflow.status,
        "current_stage": workflow.current_stage,
        "retry_count": workflow.retry_count,
        "error": workflow.error,
        "started_at": started_at,
        "completed_at": completed_at if run_finished else None,
        "paused_at": completed_at
        if workflow.status == AgentWorkflowStatus.WAITING_FOR_HUMAN
        else None,
        "elapsed_ms": duration_ms(started_at, completed_at if run_finished else observed_at),
        "total_duration_ms": total_duration_ms,
        "failed_stage_count": sum(
            1 for item in stages if item["status"] == AgentStageCheckpointStatus.FAILED
        ),
        "waiting_stage_count": sum(
            1 for item in stages if item["status"] == AgentStageCheckpointStatus.WAITING
        ),
        "completed_stage_count": sum(
            1
            for item in stages
            if item["status"] == AgentStageCheckpointStatus.COMPLETED
        ),
        "skipped_stage_count": sum(
            1 for item in stages if item["status"] == AgentStageCheckpointStatus.SKIPPED
        ),
        "token_count": _sum_optional_ints(
            [item["token_count"] for item in stages]
        ),
        "estimated_cost": _sum_optional_floats(
            [item["estimated_cost"] for item in stages]
        ),
        "api_operations": _superdocs_api_operations(db, workflow.validation_run_id),
        "stages": stages,
    }
