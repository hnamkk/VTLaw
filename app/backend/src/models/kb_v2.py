"""KB v2 foundation models.

These tables stay isolated from the current KB v1 tables so the v2 rebuild can
ship in parallel behind feature flags.
"""

from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.models.base import Base


class KbV2LegalDocument(Base):
    __tablename__ = "kb_v2_legal_documents"
    __table_args__ = (
        CheckConstraint(
            "legal_status IN ('unknown', 'future_effective', 'active', 'expired', 'suspended')",
            name="chk_kb_v2_document_legal_status",
        ),
        Index("idx_kb_v2_documents_number", "document_number"),
        Index("idx_kb_v2_documents_legal_status", "legal_status"),
    )

    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    issuing_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    legal_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'unknown'")
    )
    scope_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=sa_text("'{}'")
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    revisions: Mapped[list["KbV2DocumentRevision"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    source_assets: Mapped[list["KbV2SourceAsset"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    canonical_provisions: Mapped[list["KbV2CanonicalProvision"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    standard_summaries: Mapped[list["KbV2StandardSummary"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    metadata_proposals: Mapped[list["KbV2MetadataProposal"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    review_events: Mapped[list["KbV2ReviewEvent"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    outgoing_relations: Mapped[list["KbV2DocumentRelation"]] = relationship(
        back_populates="source_document",
        cascade="all, delete-orphan",
        foreign_keys="KbV2DocumentRelation.source_document_id",
    )
    incoming_relations: Mapped[list["KbV2DocumentRelation"]] = relationship(
        back_populates="target_document",
        cascade="all, delete-orphan",
        foreign_keys="KbV2DocumentRelation.target_document_id",
    )


class KbV2DocumentRevision(Base):
    __tablename__ = "kb_v2_document_revisions"
    __table_args__ = (
        CheckConstraint(
            "ingestion_status IN ('uploaded', 'parsing', 'parsed', 'parse_failed')",
            name="chk_kb_v2_revision_ingestion_status",
        ),
        CheckConstraint(
            "review_status IN ('needs_review', 'in_review', 'approved', 'rejected')",
            name="chk_kb_v2_revision_review_status",
        ),
        CheckConstraint(
            "publication_status IN ('draft', 'published', 'suspended', 'archived')",
            name="chk_kb_v2_revision_publication_status",
        ),
        UniqueConstraint(
            "document_id", "revision_number", name="uq_kb_v2_revision_document_revision_number"
        ),
        Index("idx_kb_v2_revisions_document_created", "document_id", "created_at"),
        Index("idx_kb_v2_revisions_status", "publication_status", "review_status"),
    )

    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_asset_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_source_assets.asset_id", ondelete="SET NULL"),
        nullable=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ingestion_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'uploaded'")
    )
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'needs_review'")
    )
    publication_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'draft'")
    )
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_downloaded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="revisions")
    source_asset: Mapped["KbV2SourceAsset | None"] = relationship(
        back_populates="linked_revisions",
        foreign_keys=[source_asset_id],
        post_update=True,
    )
    source_assets: Mapped[list["KbV2SourceAsset"]] = relationship(
        back_populates="revision",
        foreign_keys="KbV2SourceAsset.revision_id",
    )
    canonical_nodes: Mapped[list["KbV2CanonicalNode"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    retrieval_units: Mapped[list["KbV2RetrievalUnit"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    provision_versions: Mapped[list["KbV2ProvisionVersion"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    standard_summaries: Mapped[list["KbV2StandardSummary"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    metadata_proposals: Mapped[list["KbV2MetadataProposal"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )
    review_events: Mapped[list["KbV2ReviewEvent"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan"
    )


class KbV2SourceAsset(Base):
    __tablename__ = "kb_v2_source_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_role IN ('source', 'asset', 'rendition')",
            name="chk_kb_v2_source_asset_role",
        ),
        UniqueConstraint("storage_uri", name="uq_kb_v2_source_assets_storage_uri"),
        Index("idx_kb_v2_source_assets_revision_role", "revision_id", "asset_role"),
        Index("idx_kb_v2_source_assets_sha256", "sha256"),
    )

    asset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="SET NULL"),
        nullable=True,
    )
    asset_role: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_downloaded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="source_assets")
    revision: Mapped["KbV2DocumentRevision | None"] = relationship(
        back_populates="source_assets",
        foreign_keys=[revision_id],
    )
    linked_revisions: Mapped[list["KbV2DocumentRevision"]] = relationship(
        back_populates="source_asset",
        foreign_keys="KbV2DocumentRevision.source_asset_id",
    )


class KbV2CanonicalNode(Base):
    __tablename__ = "kb_v2_canonical_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('chapter', 'section', 'article', 'clause', 'point', "
            "'table', 'appendix', 'form', 'image_caption')",
            name="chk_kb_v2_canonical_node_type",
        ),
        CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_canonical_node_review_status",
        ),
        Index("idx_kb_v2_nodes_revision_order", "revision_id", "order_index"),
        Index("idx_kb_v2_nodes_parent", "parent_id"),
    )

    node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
        nullable=True,
    )
    node_type: Mapped[str] = mapped_column(String(24), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'"))
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'needs_review'")
    )
    structured_content: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    revision: Mapped["KbV2DocumentRevision"] = relationship(back_populates="canonical_nodes")
    parent: Mapped["KbV2CanonicalNode | None"] = relationship(
        remote_side=[node_id], back_populates="children"
    )
    children: Mapped[list["KbV2CanonicalNode"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    retrieval_units: Mapped[list["KbV2RetrievalUnit"]] = relationship(
        back_populates="canonical_node", cascade="all, delete-orphan"
    )
    provision_sources: Mapped[list["KbV2ProvisionSource"]] = relationship(
        back_populates="canonical_node", cascade="all, delete-orphan"
    )
    amendment_operations: Mapped[list["KbV2AmendmentOperation"]] = relationship(
        back_populates="source_canonical_node", cascade="all, delete-orphan"
    )


class KbV2RetrievalUnit(Base):
    __tablename__ = "kb_v2_retrieval_units"
    __table_args__ = (
        CheckConstraint(
            "answerable_status IN ('active', 'future', 'historical', 'suspended', "
            "'not_answerable')",
            name="chk_kb_v2_retrieval_unit_answerable_status",
        ),
        UniqueConstraint("content_hash", name="uq_kb_v2_retrieval_units_content_hash"),
        Index(
            "idx_kb_v2_retrieval_units_eligibility",
            "answerable_status",
            "effective_from",
            "effective_to",
        ),
        Index("idx_kb_v2_retrieval_units_revision", "revision_id"),
    )

    retrieval_unit_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    canonical_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIM), nullable=True
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    answerable_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'not_answerable'")
    )
    citation_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    index_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    canonical_node: Mapped["KbV2CanonicalNode"] = relationship(back_populates="retrieval_units")
    document: Mapped["KbV2LegalDocument"] = relationship()
    revision: Mapped["KbV2DocumentRevision"] = relationship(back_populates="retrieval_units")


class KbV2DocumentRelation(Base):
    __tablename__ = "kb_v2_document_relations"
    __table_args__ = (
        CheckConstraint(
            "relation_type IN ('amends', 'supplements', 'replaces', 'annuls', "
            "'guides', 'depends_on')",
            name="chk_kb_v2_document_relation_type",
        ),
        CheckConstraint(
            "source_document_id <> target_document_id",
            name="chk_kb_v2_document_relation_distinct",
        ),
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            "source_locator",
            "target_locator",
            name="uq_kb_v2_document_relation",
        ),
    )

    relation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    source_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source_document: Mapped["KbV2LegalDocument"] = relationship(
        back_populates="outgoing_relations",
        foreign_keys=[source_document_id],
    )
    target_document: Mapped["KbV2LegalDocument"] = relationship(
        back_populates="incoming_relations",
        foreign_keys=[target_document_id],
    )


class KbV2MetadataProposal(Base):
    __tablename__ = "kb_v2_metadata_proposals"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('upload', 'parser', 'ai', 'admin')",
            name="chk_kb_v2_metadata_proposal_source_type",
        ),
        CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_metadata_proposal_review_status",
        ),
        Index(
            "idx_kb_v2_metadata_proposals_revision_field",
            "revision_id",
            "field_name",
            "review_status",
        ),
    )

    proposal_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=False,
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'needs_review'")
    )
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'"))
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="metadata_proposals")
    revision: Mapped["KbV2DocumentRevision"] = relationship(back_populates="metadata_proposals")


class KbV2CanonicalProvision(Base):
    __tablename__ = "kb_v2_canonical_provisions"
    __table_args__ = (
        UniqueConstraint("document_id", "provision_key", name="uq_kb_v2_canonical_provision_key"),
        Index("idx_kb_v2_canonical_provisions_document", "document_id"),
    )

    canonical_provision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    provision_key: Mapped[str] = mapped_column(String(180), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="canonical_provisions")
    versions: Mapped[list["KbV2ProvisionVersion"]] = relationship(
        back_populates="canonical_provision", cascade="all, delete-orphan"
    )


class KbV2ProvisionVersion(Base):
    __tablename__ = "kb_v2_provision_versions"
    __table_args__ = (
        CheckConstraint(
            "answerable_status IN ('active', 'future', 'historical', 'suspended', "
            "'not_answerable')",
            name="chk_kb_v2_provision_version_answerable_status",
        ),
        Index(
            "idx_kb_v2_provision_versions_timeline",
            "canonical_provision_id",
            "effective_from",
            "effective_to",
        ),
    )

    provision_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    canonical_provision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_canonical_provisions.canonical_provision_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    answerable_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'not_answerable'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    canonical_provision: Mapped["KbV2CanonicalProvision"] = relationship(back_populates="versions")
    revision: Mapped["KbV2DocumentRevision"] = relationship(back_populates="provision_versions")
    provision_sources: Mapped[list["KbV2ProvisionSource"]] = relationship(
        back_populates="provision_version", cascade="all, delete-orphan"
    )
    amendment_operations: Mapped[list["KbV2AmendmentOperation"]] = relationship(
        back_populates="provision_version", cascade="all, delete-orphan"
    )


class KbV2ProvisionSource(Base):
    __tablename__ = "kb_v2_provision_sources"
    __table_args__ = (
        CheckConstraint(
            "source_role IN ('original', 'amendment', 'supporting')",
            name="chk_kb_v2_provision_source_role",
        ),
        UniqueConstraint(
            "provision_version_id",
            "canonical_node_id",
            "source_role",
            name="uq_kb_v2_provision_source",
        ),
    )

    provision_source_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    provision_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_provision_versions.provision_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_role: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    provision_version: Mapped["KbV2ProvisionVersion"] = relationship(
        back_populates="provision_sources"
    )
    canonical_node: Mapped["KbV2CanonicalNode"] = relationship(back_populates="provision_sources")


class KbV2AmendmentOperation(Base):
    __tablename__ = "kb_v2_amendment_operations"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('replace', 'insert', 'delete', 'append', 'amend_text')",
            name="chk_kb_v2_amendment_operation_type",
        ),
        Index(
            "idx_kb_v2_amendment_operations_version_order",
            "provision_version_id",
            "operation_order",
        ),
    )

    amendment_operation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    provision_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_provision_versions.provision_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_canonical_node_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
    )
    operation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa_text("0")
    )
    payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    provision_version: Mapped["KbV2ProvisionVersion"] = relationship(
        back_populates="amendment_operations"
    )
    source_canonical_node: Mapped["KbV2CanonicalNode | None"] = relationship(
        back_populates="amendment_operations"
    )


class KbV2StandardSummary(Base):
    __tablename__ = "kb_v2_standard_summaries"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_standard_summary_review_status",
        ),
        UniqueConstraint("revision_id", name="uq_kb_v2_standard_summary_revision"),
    )

    summary_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=sa_text("'needs_review'")
    )
    approved_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="standard_summaries")
    revision: Mapped["KbV2DocumentRevision"] = relationship(back_populates="standard_summaries")


class KbV2ReviewEvent(Base):
    __tablename__ = "kb_v2_review_events"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('document', 'revision', 'node', 'relation', "
            "'summary', 'retrieval_unit', 'provision_version')",
            name="chk_kb_v2_review_event_entity_type",
        ),
        CheckConstraint(
            "decision IN ('created', 'updated', 'approved', 'rejected', 'published', "
            "'suspended', 'archived')",
            name="chk_kb_v2_review_event_decision",
        ),
        Index("idx_kb_v2_review_events_revision_created", "revision_id", "created_at"),
        Index("idx_kb_v2_review_events_document_created", "document_id", "created_at"),
    )

    review_event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa_text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["KbV2LegalDocument"] = relationship(back_populates="review_events")
    revision: Mapped["KbV2DocumentRevision | None"] = relationship(back_populates="review_events")
