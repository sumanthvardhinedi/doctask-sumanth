from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import SuperDocsReviewStatus

if TYPE_CHECKING:
    from app.models.filing import PackageDocument
    from app.models.finding import Finding


class SuperDocsReviewSession(Base):
    __tablename__ = "superdocs_review_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("filing_packages.id"), nullable=False
    )
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_runs.id"), nullable=False
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False, unique=True
    )
    package_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("package_documents.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SuperDocsReviewStatus.PROPOSED
    )
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    edit_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    superdocs_session_id: Mapped[str | None] = mapped_column(
    String(255), nullable=True)
    job_id: Mapped[str | None] = mapped_column(
    String(255), nullable=True
    )
    proposed_changes_json: Mapped[str | None] = mapped_column(
    Text, nullable=True
    )
    export_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    human_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    finding: Mapped[Finding] = relationship()
    document: Mapped[PackageDocument] = relationship()
