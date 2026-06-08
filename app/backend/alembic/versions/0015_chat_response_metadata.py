"""Persist chat response metadata.

Revision ID: 0015_chat_response_metadata
Revises: 0014_kb_v2_review_publish
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015_chat_response_metadata"
down_revision = "0014_kb_v2_review_publish"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qa_messages",
        sa.Column(
            "response_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("qa_messages", "response_metadata")
