"""Add document lifecycle audit events.

Revision ID: 0011_document_lifecycle_events
Revises: 0010_notifications_rate_limit
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_document_lifecycle_events"
down_revision: str | None = "0010_notifications_rate_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_lifecycle_events",
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=False),
        sa.Column("previous_legal_status", sa.String(length=24), nullable=False),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("new_legal_status", sa.String(length=24), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_lifecycle_events_doc_created",
        "document_lifecycle_events",
        ["doc_id", "created_at"],
    )
    op.create_index(
        "idx_lifecycle_events_effective_on",
        "document_lifecycle_events",
        ["effective_on"],
    )


def downgrade() -> None:
    op.drop_index("idx_lifecycle_events_effective_on", table_name="document_lifecycle_events")
    op.drop_index("idx_lifecycle_events_doc_created", table_name="document_lifecycle_events")
    op.drop_table("document_lifecycle_events")
