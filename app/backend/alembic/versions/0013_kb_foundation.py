"""Add legal knowledge base foundation tables.

Revision ID: 0013_kb_v2_foundation
Revises: 0012_chat_owner_constraints
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_kb_v2_foundation"
down_revision: str | None = "0012_chat_owner_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kb_v2_legal_documents",
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("document_number", sa.String(length=120), nullable=True),
        sa.Column("document_type", sa.String(length=40), nullable=True),
        sa.Column("issuing_authority", sa.String(length=255), nullable=True),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column(
            "legal_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column(
            "scope_tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "legal_status IN ('unknown', 'future_effective', 'active', 'expired', 'suspended')",
            name="chk_kb_v2_document_legal_status",
        ),
    )
    op.create_index(
        "idx_kb_v2_documents_legal_status",
        "kb_v2_legal_documents",
        ["legal_status"],
    )
    op.create_index("idx_kb_v2_documents_number", "kb_v2_legal_documents", ["document_number"])

    op.create_table(
        "kb_v2_source_assets",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("asset_role", sa.String(length=16), nullable=False),
        sa.Column("storage_uri", sa.String(length=1000), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_downloaded_at", sa.Date(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "asset_role IN ('source', 'asset', 'rendition')",
            name="chk_kb_v2_source_asset_role",
        ),
        sa.UniqueConstraint("storage_uri", name="uq_kb_v2_source_assets_storage_uri"),
    )
    op.create_index(
        "idx_kb_v2_source_assets_revision_role",
        "kb_v2_source_assets",
        ["revision_id", "asset_role"],
    )
    op.create_index("idx_kb_v2_source_assets_sha256", "kb_v2_source_assets", ["sha256"])

    op.create_table(
        "kb_v2_document_revisions",
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_asset_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_source_assets.asset_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "ingestion_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'uploaded'"),
        ),
        sa.Column(
            "review_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "publication_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_downloaded_at", sa.Date(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "ingestion_status IN ('uploaded', 'parsing', 'parsed', 'parse_failed')",
            name="chk_kb_v2_revision_ingestion_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('needs_review', 'in_review', 'approved', 'rejected')",
            name="chk_kb_v2_revision_review_status",
        ),
        sa.CheckConstraint(
            "publication_status IN ('draft', 'published', 'suspended', 'archived')",
            name="chk_kb_v2_revision_publication_status",
        ),
        sa.UniqueConstraint(
            "document_id",
            "revision_number",
            name="uq_kb_v2_revision_document_revision_number",
        ),
    )
    op.create_index(
        "idx_kb_v2_revisions_document_created",
        "kb_v2_document_revisions",
        ["document_id", "created_at"],
    )
    op.create_index(
        "idx_kb_v2_revisions_status",
        "kb_v2_document_revisions",
        ["publication_status", "review_status"],
    )
    op.create_foreign_key(
        "fk_kb_v2_source_assets_revision_id",
        "kb_v2_source_assets",
        "kb_v2_document_revisions",
        ["revision_id"],
        ["revision_id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "kb_v2_canonical_nodes",
        sa.Column(
            "node_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("node_type", sa.String(length=24), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "review_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "structured_content",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "node_type IN ('chapter', 'section', 'article', 'clause', 'point', "
            "'table', 'appendix', 'form', 'image_caption')",
            name="chk_kb_v2_canonical_node_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_canonical_node_review_status",
        ),
    )
    op.create_index(
        "idx_kb_v2_nodes_revision_order",
        "kb_v2_canonical_nodes",
        ["revision_id", "order_index"],
    )
    op.create_index("idx_kb_v2_nodes_parent", "kb_v2_canonical_nodes", ["parent_id"])

    op.create_table(
        "kb_v2_document_relations",
        sa.Column(
            "relation_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(length=24), nullable=False),
        sa.Column("source_locator", sa.String(length=255), nullable=True),
        sa.Column("target_locator", sa.String(length=255), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "relation_type IN ('amends', 'supplements', 'replaces', 'annuls', "
            "'guides', 'depends_on')",
            name="chk_kb_v2_document_relation_type",
        ),
        sa.CheckConstraint(
            "source_document_id <> target_document_id",
            name="chk_kb_v2_document_relation_distinct",
        ),
        sa.UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            "source_locator",
            "target_locator",
            name="uq_kb_v2_document_relation",
        ),
    )

    op.create_table(
        "kb_v2_canonical_provisions",
        sa.Column(
            "canonical_provision_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provision_key", sa.String(length=180), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "document_id",
            "provision_key",
            name="uq_kb_v2_canonical_provision_key",
        ),
    )
    op.create_index(
        "idx_kb_v2_canonical_provisions_document",
        "kb_v2_canonical_provisions",
        ["document_id"],
    )

    op.create_table(
        "kb_v2_provision_versions",
        sa.Column(
            "provision_version_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "canonical_provision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_canonical_provisions.canonical_provision_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "answerable_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'not_answerable'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "answerable_status IN ('active', 'future', 'historical', 'suspended', "
            "'not_answerable')",
            name="chk_kb_v2_provision_version_answerable_status",
        ),
    )
    op.create_index(
        "idx_kb_v2_provision_versions_timeline",
        "kb_v2_provision_versions",
        ["canonical_provision_id", "effective_from", "effective_to"],
    )

    op.create_table(
        "kb_v2_provision_sources",
        sa.Column(
            "provision_source_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "provision_version_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_provision_versions.provision_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "canonical_node_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_role", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source_role IN ('original', 'amendment', 'supporting')",
            name="chk_kb_v2_provision_source_role",
        ),
        sa.UniqueConstraint(
            "provision_version_id",
            "canonical_node_id",
            "source_role",
            name="uq_kb_v2_provision_source",
        ),
    )

    op.create_table(
        "kb_v2_amendment_operations",
        sa.Column(
            "amendment_operation_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "provision_version_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_provision_versions.provision_version_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_canonical_node_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operation_type", sa.String(length=24), nullable=False),
        sa.Column("target_locator", sa.String(length=255), nullable=True),
        sa.Column(
            "operation_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "operation_type IN ('replace', 'insert', 'delete', 'append', 'amend_text')",
            name="chk_kb_v2_amendment_operation_type",
        ),
    )
    op.create_index(
        "idx_kb_v2_amendment_operations_version_order",
        "kb_v2_amendment_operations",
        ["provision_version_id", "operation_order"],
    )

    op.create_table(
        "kb_v2_retrieval_units",
        sa.Column(
            "retrieval_unit_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "canonical_node_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_canonical_nodes.node_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_vector", Vector(1536), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "answerable_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'not_answerable'"),
        ),
        sa.Column("citation_label", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=80), nullable=True),
        sa.Column("embedding_version", sa.String(length=40), nullable=True),
        sa.Column("index_version", sa.String(length=40), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "answerable_status IN ('active', 'future', 'historical', 'suspended', "
            "'not_answerable')",
            name="chk_kb_v2_retrieval_unit_answerable_status",
        ),
        sa.UniqueConstraint("content_hash", name="uq_kb_v2_retrieval_units_content_hash"),
    )
    op.create_index(
        "idx_kb_v2_retrieval_units_eligibility",
        "kb_v2_retrieval_units",
        ["answerable_status", "effective_from", "effective_to"],
    )
    op.create_index(
        "idx_kb_v2_retrieval_units_revision",
        "kb_v2_retrieval_units",
        ["revision_id"],
    )

    op.create_table(
        "kb_v2_standard_summaries",
        sa.Column(
            "summary_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "review_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_standard_summary_review_status",
        ),
        sa.UniqueConstraint("revision_id", name="uq_kb_v2_standard_summary_revision"),
    )

    op.create_table(
        "kb_v2_review_events",
        sa.Column(
            "review_event_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_legal_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_v2_document_revisions.revision_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "entity_type IN ('document', 'revision', 'node', 'relation', "
            "'summary', 'retrieval_unit', 'provision_version')",
            name="chk_kb_v2_review_event_entity_type",
        ),
        sa.CheckConstraint(
            "decision IN ('created', 'updated', 'approved', 'rejected', 'published', "
            "'suspended', 'archived')",
            name="chk_kb_v2_review_event_decision",
        ),
    )
    op.create_index(
        "idx_kb_v2_review_events_revision_created",
        "kb_v2_review_events",
        ["revision_id", "created_at"],
    )
    op.create_index(
        "idx_kb_v2_review_events_document_created",
        "kb_v2_review_events",
        ["document_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_kb_v2_review_events_document_created",
        table_name="kb_v2_review_events",
    )
    op.drop_index(
        "idx_kb_v2_review_events_revision_created",
        table_name="kb_v2_review_events",
    )
    op.drop_table("kb_v2_review_events")

    op.drop_table("kb_v2_standard_summaries")

    op.drop_index(
        "idx_kb_v2_retrieval_units_revision",
        table_name="kb_v2_retrieval_units",
    )
    op.drop_index(
        "idx_kb_v2_retrieval_units_eligibility",
        table_name="kb_v2_retrieval_units",
    )
    op.drop_table("kb_v2_retrieval_units")

    op.drop_index(
        "idx_kb_v2_amendment_operations_version_order",
        table_name="kb_v2_amendment_operations",
    )
    op.drop_table("kb_v2_amendment_operations")

    op.drop_table("kb_v2_provision_sources")

    op.drop_index(
        "idx_kb_v2_provision_versions_timeline",
        table_name="kb_v2_provision_versions",
    )
    op.drop_table("kb_v2_provision_versions")

    op.drop_index(
        "idx_kb_v2_canonical_provisions_document",
        table_name="kb_v2_canonical_provisions",
    )
    op.drop_table("kb_v2_canonical_provisions")

    op.drop_table("kb_v2_document_relations")

    op.drop_index("idx_kb_v2_nodes_parent", table_name="kb_v2_canonical_nodes")
    op.drop_index(
        "idx_kb_v2_nodes_revision_order",
        table_name="kb_v2_canonical_nodes",
    )
    op.drop_table("kb_v2_canonical_nodes")

    op.drop_constraint(
        "fk_kb_v2_source_assets_revision_id",
        "kb_v2_source_assets",
        type_="foreignkey",
    )

    op.drop_index(
        "idx_kb_v2_revisions_status",
        table_name="kb_v2_document_revisions",
    )
    op.drop_index(
        "idx_kb_v2_revisions_document_created",
        table_name="kb_v2_document_revisions",
    )
    op.drop_table("kb_v2_document_revisions")

    op.drop_index(
        "idx_kb_v2_source_assets_sha256",
        table_name="kb_v2_source_assets",
    )
    op.drop_index(
        "idx_kb_v2_source_assets_revision_role",
        table_name="kb_v2_source_assets",
    )
    op.drop_table("kb_v2_source_assets")

    op.drop_index(
        "idx_kb_v2_documents_number",
        table_name="kb_v2_legal_documents",
    )
    op.drop_index(
        "idx_kb_v2_documents_legal_status",
        table_name="kb_v2_legal_documents",
    )
    op.drop_table("kb_v2_legal_documents")
