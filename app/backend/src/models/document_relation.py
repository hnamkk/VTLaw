"""Directed legal-document relationships."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.legal_document import LegalDocument


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    relation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(180), nullable=True)
    target_locator: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source_document: Mapped["LegalDocument"] = relationship(
        foreign_keys=[source_doc_id], back_populates="outgoing_relations"
    )
    target_document: Mapped["LegalDocument"] = relationship(
        foreign_keys=[target_doc_id], back_populates="incoming_relations"
    )

    __table_args__ = (
        CheckConstraint(
            "relation_type IN ('promulgates', 'amends', 'replaces', "
            "'partially_repeals', 'fully_repeals', 'implements', 'attachment_of')",
            name="chk_document_relation_type",
        ),
        CheckConstraint("source_doc_id <> target_doc_id", name="chk_document_relation_distinct"),
        UniqueConstraint(
            "source_doc_id",
            "target_doc_id",
            "relation_type",
            "source_locator",
            "target_locator",
            name="uq_document_relation",
        ),
    )
