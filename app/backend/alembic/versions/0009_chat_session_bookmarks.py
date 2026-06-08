"""Add bookmarks to chat sessions.

Revision ID: 0009_chat_session_bookmarks
Revises: 0008_quality_evidence
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_chat_session_bookmarks"
down_revision: str | None = "0008_quality_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "qa_sessions",
        sa.Column("is_bookmarked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("qa_sessions", sa.Column("bookmark_title", sa.String(length=120), nullable=True))
    op.add_column("qa_sessions", sa.Column("bookmarked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_qa_sessions_user_bookmarked", "qa_sessions", ["user_id", "is_bookmarked", "bookmarked_at"])


def downgrade() -> None:
    op.drop_index("idx_qa_sessions_user_bookmarked", table_name="qa_sessions")
    op.drop_column("qa_sessions", "bookmarked_at")
    op.drop_column("qa_sessions", "bookmark_title")
    op.drop_column("qa_sessions", "is_bookmarked")
