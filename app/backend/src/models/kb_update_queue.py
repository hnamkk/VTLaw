"""Human-review queue for knowledge-base document changes."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.legal_document import LegalDocument


class KbUpdateQueue(Base):
    __tablename__ = "kb_update_queue"

    queue_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_doc_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="SET NULL"),
        nullable=True,
    )
    change_type: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        server_default=text("'create'"),
    )
    review_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'pending'"),
    )
    processing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'ready'"),
    )
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parser_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning_messages: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        server_default=text("'{}'"),
    )
    extracted_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )
    review_checklist: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'"),
    )
    reviewer_draft_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped["LegalDocument"] = relationship(
        foreign_keys=[doc_id],
        back_populates="queue_items",
    )
    target_document: Mapped["LegalDocument | None"] = relationship(
        foreign_keys=[target_doc_id],
    )

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('create', 'update', 'repeal')",
            name="chk_kb_queue_change_type",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="chk_kb_queue_review_status",
        ),
        CheckConstraint(
            "processing_status IN ('queued', 'ready', 'failed')",
            name="chk_kb_queue_processing_status",
        ),
    )
