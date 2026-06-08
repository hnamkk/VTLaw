"""add corpus lifecycle, document assets, and traffic-sign catalog

Revision ID: 0003_corpus_lifecycle_assets
Revises: 0002_kb_update_queue
Create Date: 2026-06-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_corpus_lifecycle_assets"
down_revision: Union[str, None] = "0002_kb_update_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("chk_doc_type", "legal_documents", type_="check")
    op.add_column("legal_documents", sa.Column("document_number", sa.String(100)))
    op.add_column("legal_documents", sa.Column("document_family", sa.String(100)))
    op.add_column(
        "legal_documents",
        sa.Column("review_status", sa.String(16), nullable=False, server_default="approved"),
    )
    op.add_column(
        "legal_documents",
        sa.Column("legal_status", sa.String(24), nullable=False, server_default="active"),
    )
    op.add_column(
        "legal_documents",
        sa.Column("rag_scope", sa.String(24), nullable=False, server_default="enabled"),
    )
    op.add_column(
        "legal_documents",
        sa.Column("rag_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("legal_documents", sa.Column("valid_from", sa.Date()))
    op.add_column("legal_documents", sa.Column("valid_to", sa.Date()))
    op.add_column("legal_documents", sa.Column("source_checksum", sa.String(64)))
    op.add_column(
        "legal_documents",
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "legal_documents",
        sa.Column("parser_profile", sa.String(40), nullable=False, server_default="legal"),
    )
    op.add_column(
        "legal_documents",
        sa.Column("parser_version", sa.String(40), nullable=False, server_default="legal-v1"),
    )
    op.add_column("legal_documents", sa.Column("index_version", sa.String(40)))
    op.add_column(
        "legal_documents", sa.Column("official_status_checked_at", sa.DateTime(timezone=True))
    )
    op.add_column("legal_documents", sa.Column("official_status_source_url", sa.String(500)))
    op.execute("UPDATE legal_documents SET valid_from = effective_date WHERE valid_from IS NULL")
    op.execute("UPDATE legal_documents SET valid_to = expiry_date WHERE valid_to IS NULL")
    op.create_check_constraint(
        "chk_doc_type",
        "legal_documents",
        "doc_type IN ('LUAT', 'BO_LUAT', 'NGHI_DINH', 'THONG_TU', "
        "'QUYET_DINH', 'CONG_VAN', 'QUY_CHUAN')",
    )
    op.create_check_constraint(
        "chk_legal_docs_review_status",
        "legal_documents",
        "review_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        "chk_legal_docs_legal_status",
        "legal_documents",
        "legal_status IN ('future_effective', 'active', 'partially_repealed', 'repealed')",
    )
    op.create_check_constraint(
        "chk_legal_docs_rag_scope",
        "legal_documents",
        "rag_scope IN ('enabled', 'disabled', 'selective')",
    )
    op.create_index("idx_legal_docs_document_number", "legal_documents", ["document_number"])
    op.create_index(
        "idx_legal_docs_searchable",
        "legal_documents",
        ["status", "rag_enabled", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_legal_docs_number_trgm",
        "legal_documents",
        ["document_number"],
        postgresql_using="gin",
        postgresql_ops={"document_number": "gin_trgm_ops"},
    )

    op.drop_constraint("chk_chunk_type", "document_chunks", type_="check")
    op.drop_constraint("chk_chunk_hierarchy", "document_chunks", type_="check")
    op.alter_column(
        "document_chunks",
        "chunk_type",
        existing_type=sa.String(10),
        type_=sa.String(32),
        existing_nullable=False,
    )
    op.add_column("document_chunks", sa.Column("canonical_provision_id", sa.String(180)))
    op.add_column("document_chunks", sa.Column("locator_type", sa.String(24)))
    op.add_column("document_chunks", sa.Column("locator_label", sa.String(180)))
    op.add_column(
        "document_chunks",
        sa.Column(
            "section_path",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("document_chunks", sa.Column("section_number", sa.String(60)))
    op.add_column(
        "document_chunks",
        sa.Column(
            "sign_codes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "figure_ids",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("document_chunks", sa.Column("table_id", sa.String(80)))
    op.add_column(
        "document_chunks",
        sa.Column(
            "asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("corpus", sa.String(32), nullable=False, server_default="road_law"),
    )
    op.add_column(
        "document_chunks",
        sa.Column("rag_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("document_chunks", sa.Column("valid_from", sa.Date()))
    op.add_column("document_chunks", sa.Column("valid_to", sa.Date()))
    op.add_column(
        "document_chunks",
        sa.Column("provision_status", sa.String(24), nullable=False, server_default="active"),
    )
    op.add_column("document_chunks", sa.Column("content_hash", sa.String(64)))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(80)))
    op.add_column("document_chunks", sa.Column("embedding_version", sa.String(40)))
    op.add_column("document_chunks", sa.Column("parser_version", sa.String(40)))
    op.execute("UPDATE document_chunks SET valid_from = effective_date WHERE valid_from IS NULL")
    op.create_check_constraint(
        "chk_chunk_type",
        "document_chunks",
        "chunk_type IN ('chuong', 'dieu', 'khoan', 'diem', 'phu_luc', "
        "'technical_section', 'definition', 'sign_group', 'sign_definition', "
        "'installation_rule', 'table', 'figure_caption', 'appendix_item')",
    )
    op.create_check_constraint(
        "chk_chunk_hierarchy",
        "document_chunks",
        "(chunk_type = 'chuong' AND chapter_num IS NOT NULL) OR "
        "(chunk_type IN ('dieu', 'khoan', 'diem') AND article_num IS NOT NULL) OR "
        "(chunk_type IN ('phu_luc', 'technical_section', 'definition', 'sign_group', "
        "'sign_definition', 'installation_rule', 'table', 'figure_caption', "
        "'appendix_item'))",
    )
    op.create_check_constraint(
        "chk_chunk_provision_status",
        "document_chunks",
        "provision_status IN ('future_effective', 'active', 'repealed')",
    )
    op.create_index(
        "idx_chunks_searchable",
        "document_chunks",
        ["status", "rag_enabled", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_chunks_canonical_provision",
        "document_chunks",
        ["canonical_provision_id", "valid_from"],
    )
    op.create_index(
        "idx_chunks_sign_codes",
        "document_chunks",
        ["sign_codes"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_chunks_content_hash", "document_chunks", ["content_hash"]
    )

    op.create_table(
        "document_relations",
        sa.Column(
            "relation_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "source_doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(24), nullable=False),
        sa.Column("source_locator", sa.String(180)),
        sa.Column("target_locator", sa.String(180)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "relation_type IN ('promulgates', 'amends', 'replaces', "
            "'partially_repeals', 'fully_repeals', 'implements', 'attachment_of')",
            name="chk_document_relation_type",
        ),
        sa.CheckConstraint(
            "source_doc_id <> target_doc_id", name="chk_document_relation_distinct"
        ),
        sa.UniqueConstraint(
            "source_doc_id",
            "target_doc_id",
            "relation_type",
            "source_locator",
            "target_locator",
            name="uq_document_relation",
        ),
    )
    op.create_index("idx_document_rel_source", "document_relations", ["source_doc_id"])
    op.create_index("idx_document_rel_target", "document_relations", ["target_doc_id"])

    op.create_table(
        "document_assets",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_kind", sa.String(24), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("source_locator", sa.String(180)),
        sa.Column("relationship_id", sa.String(100)),
        sa.Column("original_format", sa.String(20)),
        sa.Column("display_format", sa.String(20)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("original_asset_key", sa.String(500), nullable=False),
        sa.Column("display_asset_key", sa.String(500)),
        sa.Column("thumbnail_asset_key", sa.String(500)),
        sa.Column("publish_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("duplicate_group", sa.String(64)),
        sa.Column("perceptual_hash", sa.String(128)),
        sa.Column("caption", sa.Text()),
        sa.Column("alt_text", sa.Text()),
        sa.Column("mapping_confidence", sa.String(12), nullable=False, server_default="low"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=False)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "asset_kind IN ('source', 'pdf_rendition', 'sign_image', "
            "'sign_group', 'figure', 'table_image')",
            name="chk_document_asset_kind",
        ),
        sa.CheckConstraint(
            "publish_status IN ('pending', 'approved', 'rejected', 'private')",
            name="chk_document_asset_publish_status",
        ),
        sa.CheckConstraint(
            "mapping_confidence IN ('high', 'medium', 'low')",
            name="chk_document_asset_mapping_confidence",
        ),
        sa.UniqueConstraint("doc_id", "checksum", "asset_kind", name="uq_document_asset_checksum"),
    )
    op.create_index("idx_document_assets_doc", "document_assets", ["doc_id"])
    op.create_index(
        "idx_document_assets_public", "document_assets", ["publish_status", "asset_kind"]
    )

    op.create_table(
        "traffic_signs",
        sa.Column(
            "sign_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sign_code", sa.String(40), nullable=False),
        sa.Column("normalized_code", sa.String(40), nullable=False, unique=True),
        sa.Column("sign_name", sa.String(255), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("sign_group", sa.String(80)),
        sa.Column("meaning_text", sa.Text(), nullable=False),
        sa.Column("recognition_text", sa.Text()),
        sa.Column("application_text", sa.Text()),
        sa.Column("exception_text", sa.Text()),
        sa.Column(
            "source_chunk_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("document_chunks.chunk_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_section_path",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "primary_asset_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("document_assets.asset_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "related_asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=False)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("status", sa.String(15), nullable=False, server_default="active"),
        sa.Column("valid_from", sa.Date()),
        sa.Column("valid_to", sa.Date()),
        sa.Column("review_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "status IN ('active', 'repealed', 'pending_review')",
            name="chk_traffic_sign_status",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="chk_traffic_sign_review_status",
        ),
    )
    op.create_index(
        "idx_traffic_signs_name_trgm",
        "traffic_signs",
        ["sign_name"],
        postgresql_using="gin",
        postgresql_ops={"sign_name": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_traffic_signs_aliases", "traffic_signs", ["aliases"], postgresql_using="gin"
    )
    op.create_index(
        "idx_traffic_signs_public",
        "traffic_signs",
        ["status", "review_status", "valid_from", "valid_to"],
    )


def downgrade() -> None:
    op.drop_table("traffic_signs")
    op.drop_table("document_assets")
    op.drop_table("document_relations")

    for index in (
        "idx_chunks_content_hash",
        "idx_chunks_sign_codes",
        "idx_chunks_canonical_provision",
        "idx_chunks_searchable",
    ):
        op.drop_index(index, table_name="document_chunks")
    op.drop_constraint("chk_chunk_provision_status", "document_chunks", type_="check")
    op.drop_constraint("chk_chunk_hierarchy", "document_chunks", type_="check")
    op.drop_constraint("chk_chunk_type", "document_chunks", type_="check")
    for column in (
        "parser_version",
        "embedding_version",
        "embedding_model",
        "content_hash",
        "provision_status",
        "valid_to",
        "valid_from",
        "rag_enabled",
        "corpus",
        "asset_ids",
        "table_id",
        "figure_ids",
        "sign_codes",
        "section_number",
        "section_path",
        "locator_label",
        "locator_type",
        "canonical_provision_id",
    ):
        op.drop_column("document_chunks", column)
    op.alter_column(
        "document_chunks",
        "chunk_type",
        existing_type=sa.String(32),
        type_=sa.String(10),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "chk_chunk_type",
        "document_chunks",
        "chunk_type IN ('chuong', 'dieu', 'khoan', 'diem', 'phu_luc')",
    )
    op.create_check_constraint(
        "chk_chunk_hierarchy",
        "document_chunks",
        "(chunk_type = 'chuong' AND chapter_num IS NOT NULL) OR "
        "(chunk_type IN ('dieu', 'khoan', 'diem') AND article_num IS NOT NULL) OR "
        "(chunk_type = 'phu_luc')",
    )

    op.drop_index("idx_legal_docs_number_trgm", table_name="legal_documents")
    op.drop_index("idx_legal_docs_searchable", table_name="legal_documents")
    op.drop_index("idx_legal_docs_document_number", table_name="legal_documents")
    op.drop_constraint("chk_legal_docs_rag_scope", "legal_documents", type_="check")
    op.drop_constraint("chk_legal_docs_legal_status", "legal_documents", type_="check")
    op.drop_constraint("chk_legal_docs_review_status", "legal_documents", type_="check")
    op.drop_constraint("chk_doc_type", "legal_documents", type_="check")
    for column in (
        "official_status_source_url",
        "official_status_checked_at",
        "index_version",
        "parser_version",
        "parser_profile",
        "source_version",
        "source_checksum",
        "valid_to",
        "valid_from",
        "rag_enabled",
        "rag_scope",
        "legal_status",
        "review_status",
        "document_family",
        "document_number",
    ):
        op.drop_column("legal_documents", column)
    op.create_check_constraint(
        "chk_doc_type",
        "legal_documents",
        "doc_type IN ('LUAT', 'NGHI_DINH', 'THONG_TU', 'QUYET_DINH', 'CONG_VAN')",
    )
