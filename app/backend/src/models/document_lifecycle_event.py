"""Audit trail for automatic and reviewer-approved document lifecycle changes."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class DocumentLifecycleEvent(Base):
    __tablename__ = "document_lifecycle_events"
    __table_args__ = (
        Index("idx_lifecycle_events_doc_created", "doc_id", "created_at"),
        Index("idx_lifecycle_events_effective_on", "effective_on"),
    )

    event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_on: Mapped[date] = mapped_column(Date, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_legal_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_legal_status: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
