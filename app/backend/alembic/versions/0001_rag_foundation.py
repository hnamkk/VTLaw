"""create legal_documents and document_chunks

Revision ID: 0001_rag_foundation
Revises:
Create Date: 2026-06-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_rag_foundation"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Extensions ----
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')

    # ---- legal_documents ----
    op.create_table(
        "legal_documents",
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(15),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column(
            "replaced_by_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("issuer", sa.String(100), nullable=False),
        sa.Column(
            "domain_tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "doc_type IN ('LUAT', 'NGHI_DINH', 'THONG_TU', 'QUYET_DINH', 'CONG_VAN')",
            name="chk_doc_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'repealed', 'pending_review')",
            name="chk_doc_status",
        ),
        sa.CheckConstraint(
            "expiry_date IS NULL OR expiry_date > effective_date",
            name="chk_expiry_after_effective",
        ),
    )
    op.create_index("idx_legal_docs_status", "legal_documents", ["status"])
    op.create_index("idx_legal_docs_doc_type", "legal_documents", ["doc_type"])
    op.create_index(
        "idx_legal_docs_effective_date", "legal_documents", ["effective_date"]
    )
    op.create_index(
        "idx_legal_docs_domain_tags",
        "legal_documents",
        ["domain_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_legal_docs_active",
        "legal_documents",
        ["effective_date"],
        postgresql_where=sa.text("status = 'active'"),
    )
    # Self-referencing FK lookup (validity_checker tra văn bản thay thế qua replaced_by_id).
    op.create_index(
        "idx_legal_docs_replaced_by", "legal_documents", ["replaced_by_id"]
    )

    # ---- document_chunks ----
    op.create_table(
        "document_chunks",
        sa.Column(
            "chunk_id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("chunk_type", sa.String(10), nullable=False),
        sa.Column("chapter_num", sa.Integer(), nullable=True),
        sa.Column("article_num", sa.Integer(), nullable=True),
        sa.Column("clause_num", sa.Integer(), nullable=True),
        sa.Column("point_num", sa.String(10), nullable=True),
        sa.Column(
            "status",
            sa.String(15),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("embedding_vector", Vector(1536), nullable=True),
        sa.Column(
            "text_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text_content)", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "chunk_type IN ('chuong', 'dieu', 'khoan', 'diem', 'phu_luc')",
            name="chk_chunk_type",
        ),
        sa.CheckConstraint(
            "(chunk_type = 'chuong' AND chapter_num IS NOT NULL) OR "
            "(chunk_type IN ('dieu', 'khoan', 'diem') AND article_num IS NOT NULL) OR "
            "(chunk_type = 'phu_luc')",
            name="chk_chunk_hierarchy",
        ),
    )
    op.create_index("idx_chunks_doc_id", "document_chunks", ["doc_id"])
    op.create_index("idx_chunks_status", "document_chunks", ["status"])
    op.create_index(
        "idx_chunks_article",
        "document_chunks",
        ["doc_id", "article_num", "clause_num"],
    )
    op.create_index(
        "idx_chunks_metadata",
        "document_chunks",
        ["metadata_json"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_chunks_embedding",
        "document_chunks",
        ["embedding_vector"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
    )
    op.create_index(
        "idx_chunks_fts",
        "document_chunks",
        ["text_tsv"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_chunks_active",
        "document_chunks",
        ["doc_id", "chunk_type"],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("legal_documents")
