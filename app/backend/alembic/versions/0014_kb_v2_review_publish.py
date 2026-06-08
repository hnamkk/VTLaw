"""Add KB v2 review, proposal, and publish support.

Revision ID: 0014_kb_v2_review_publish
Revises: 0013_kb_v2_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_kb_v2_review_publish"
down_revision: str | None = "0013_kb_v2_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kb_v2_legal_documents",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    op.create_table(
        "kb_v2_metadata_proposals",
        sa.Column(
            "proposal_id",
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
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("proposed_value", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'needs_review'"),
        ),
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
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
            "source_type IN ('upload', 'parser', 'ai', 'admin')",
            name="chk_kb_v2_metadata_proposal_source_type",
        ),
        sa.CheckConstraint(
            "review_status IN ('needs_review', 'approved', 'rejected')",
            name="chk_kb_v2_metadata_proposal_review_status",
        ),
    )
    op.create_index(
        "idx_kb_v2_metadata_proposals_revision_field",
        "kb_v2_metadata_proposals",
        ["revision_id", "field_name", "review_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_kb_v2_metadata_proposals_revision_field",
        table_name="kb_v2_metadata_proposals",
    )
    op.drop_table("kb_v2_metadata_proposals")
    op.drop_column("kb_v2_legal_documents", "metadata_json")
