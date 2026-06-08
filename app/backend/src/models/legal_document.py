"""Legal document model (root regulatory text)."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.document_asset import DocumentAsset
    from src.models.document_chunk import DocumentChunk
    from src.models.document_relation import DocumentRelation
    from src.models.kb_update_queue import KbUpdateQueue


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'active'"))
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'approved'")
    )
    legal_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'active'")
    )
    rag_scope: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'enabled'")
    )
    rag_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    issuer: Mapped[str] = mapped_column(String(100), nullable=False)
    domain_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    # NOTE: schema defines this as NOT NULL FK -> users(user_id). The users table is
    # owned by the auth team and is absent from the RAG-only migration, so we keep this
    # as a nullable plain UUID here; the FK can be added once users exists.
    uploaded_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    parser_profile: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'legal'")
    )
    parser_version: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'legal-v1'")
    )
    index_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    official_status_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    official_status_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    queue_items: Mapped[list["KbUpdateQueue"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="KbUpdateQueue.doc_id",
    )
    assets: Mapped[list["DocumentAsset"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    outgoing_relations: Mapped[list["DocumentRelation"]] = relationship(
        back_populates="source_document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentRelation.source_doc_id",
    )
    incoming_relations: Mapped[list["DocumentRelation"]] = relationship(
        back_populates="target_document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentRelation.target_doc_id",
    )

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('LUAT', 'BO_LUAT', 'NGHI_DINH', 'THONG_TU', "
            "'QUYET_DINH', 'CONG_VAN', 'QUY_CHUAN')",
            name="chk_doc_type",
        ),
        CheckConstraint(
            "status IN ('active', 'repealed', 'pending_review')",
            name="chk_doc_status",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR expiry_date > effective_date",
            name="chk_expiry_after_effective",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="chk_legal_docs_review_status",
        ),
        CheckConstraint(
            "legal_status IN ('future_effective', 'active', 'partially_repealed', 'repealed')",
            name="chk_legal_docs_legal_status",
        ),
        CheckConstraint(
            "rag_scope IN ('enabled', 'disabled', 'selective')",
            name="chk_legal_docs_rag_scope",
        ),
        Index("idx_legal_docs_replaced_by", "replaced_by_id"),
        Index("idx_legal_docs_document_number", "document_number"),
        Index("idx_legal_docs_searchable", "status", "rag_enabled", "valid_from", "valid_to"),
        Index(
            "uq_legal_docs_source_checksum",
            "source_checksum",
            unique=True,
            postgresql_where=text("source_checksum IS NOT NULL"),
        ),
    )
