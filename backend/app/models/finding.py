import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import FindingResult, FindingSeverity


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    validation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("validation_runs.id"), nullable=False
    )
    package_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("package_documents.id"), nullable=True
    )
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FindingSeverity.ERROR
    )
    result: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FindingResult.FAIL
    )
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    is_hard_rejection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    validation_run: Mapped["ValidationRun"] = relationship(back_populates="findings")
    document: Mapped["PackageDocument | None"] = relationship(back_populates="findings")
    approval_decision: Mapped["ApprovalDecision | None"] = relationship(
        back_populates="finding", uselist=False, cascade="all, delete-orphan"
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False, unique=True
    )
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    finding: Mapped["Finding"] = relationship(back_populates="approval_decision")
