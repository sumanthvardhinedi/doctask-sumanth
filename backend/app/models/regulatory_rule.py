import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class IndexedRule(Base):
    __tablename__ = "indexed_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    authority_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    is_hard_rejection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_citation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    effective_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)

    if HAS_PGVECTOR:
        embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("authority_code", "rule_id", name="uq_indexed_rules_authority_rule"),
    )
