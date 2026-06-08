"""Add in-app notifications.

Revision ID: 0010_notifications_rate_limit
Revises: 0009_chat_session_bookmarks
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_notifications_rate_limit"
down_revision: str | None = "0009_chat_session_bookmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "in_app_notifications",
        sa.Column(
            "notification_id",
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
        sa.Column(
            "queue_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("kb_update_queue.queue_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("change_type", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_notifications_created_at", "in_app_notifications", ["created_at"])
    op.create_index("idx_notifications_doc_created", "in_app_notifications", ["doc_id", "created_at"])

    op.create_table(
        "user_notification_reads",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("in_app_notifications.notification_id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "notification_id", name="uq_user_notification_read"),
    )
    op.create_index("idx_notif_reads_user", "user_notification_reads", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_notif_reads_user", table_name="user_notification_reads")
    op.drop_table("user_notification_reads")
    op.drop_index("idx_notifications_doc_created", table_name="in_app_notifications")
    op.drop_index("idx_notifications_created_at", table_name="in_app_notifications")
    op.drop_table("in_app_notifications")
