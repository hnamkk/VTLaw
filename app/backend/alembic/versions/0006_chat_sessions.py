"""add per-user chat sessions

Revision ID: 0006_chat_sessions
Revises: 0005_users_auth
Create Date: 2026-06-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_chat_sessions"
down_revision: Union[str, None] = "0005_users_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_qa_sessions_user_updated", "qa_sessions", ["user_id", "updated_at"])
    op.create_index("idx_qa_sessions_user_created", "qa_sessions", ["user_id", "created_at"])

    op.create_table(
        "qa_messages",
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("qa_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("is_out_of_scope", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_qa_messages_role"),
    )
    op.create_index("idx_qa_messages_session_created", "qa_messages", ["session_id", "created_at"])
    op.create_index("idx_qa_messages_user_created", "qa_messages", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_qa_messages_user_created", table_name="qa_messages")
    op.drop_index("idx_qa_messages_session_created", table_name="qa_messages")
    op.drop_table("qa_messages")
    op.drop_index("idx_qa_sessions_user_created", table_name="qa_sessions")
    op.drop_index("idx_qa_sessions_user_updated", table_name="qa_sessions")
    op.drop_table("qa_sessions")
