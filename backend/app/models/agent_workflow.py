from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import (
    AgentStageCheckpointStatus,
    AgentWorkflowStage,
    AgentWorkflowStatus,
)

if TYPE_CHECKING:
    from app.models.filing import FilingPackage
    from app.models.validation import ValidationRun


class AgentWorkflow(Base):
    __tablename__ = "agent_workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing_packages.id"), nullable=False, index=True
    )
    validation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_runs.id"), nullable=True
    )
    authority_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AgentWorkflowStatus.PENDING
    )
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    package: Mapped[FilingPackage] = relationship()
    validation_run: Mapped[ValidationRun | None] = relationship()
    checkpoints: Mapped[list[AgentStageCheckpoint]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class AgentStageCheckpoint(Base):
    __tablename__ = "agent_stage_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_workflows.id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default=AgentWorkflowStage.INGEST_PACKAGE
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AgentStageCheckpointStatus.COMPLETED
    )
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_operation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    workflow: Mapped[AgentWorkflow] = relationship(back_populates="checkpoints")

    __table_args__ = (
        UniqueConstraint("workflow_id", "stage", name="uq_agent_checkpoint_workflow_stage"),
    )
