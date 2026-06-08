"""create kb_update_queue

Revision ID: 0002_kb_update_queue
Revises: 0001_rag_foundation
Create Date: 2026-06-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_kb_update_queue"
down_revision: Union[str, None] = "0001_rag_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kb_update_queue",
        sa.Column(
            "queue_id",
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
        sa.Column(
            "target_doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "change_type",
            sa.String(12),
            nullable=False,
            server_default=sa.text("'create'"),
        ),
        sa.Column(
            "review_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "processing_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'ready'"),
        ),
        sa.Column("source_file_name", sa.String(255), nullable=True),
        sa.Column("source_path", sa.String(500), nullable=True),
        sa.Column("parser_confidence", sa.Float(), nullable=True),
        sa.Column(
            "warning_messages",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "extracted_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "review_checklist",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("reviewer_draft_note", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.String(40), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
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
            "change_type IN ('create', 'update', 'repeal')",
            name="chk_kb_queue_change_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="chk_kb_queue_review_status",
        ),
        sa.CheckConstraint(
            "processing_status IN ('queued', 'ready', 'failed')",
            name="chk_kb_queue_processing_status",
        ),
    )
    op.create_index("idx_kb_queue_doc_id", "kb_update_queue", ["doc_id"])
    op.create_index("idx_kb_queue_target_doc_id", "kb_update_queue", ["target_doc_id"])
    op.create_index("idx_kb_queue_review_status", "kb_update_queue", ["review_status"])
    op.create_index("idx_kb_queue_processing_status", "kb_update_queue", ["processing_status"])
    op.create_index("idx_kb_queue_created_at", "kb_update_queue", ["created_at"])


def downgrade() -> None:
    op.drop_table("kb_update_queue")
