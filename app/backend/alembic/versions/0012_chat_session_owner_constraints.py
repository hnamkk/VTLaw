"""Enforce chat message ownership at the database layer.

Revision ID: 0012_chat_owner_constraints
Revises: 0011_document_lifecycle_events
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_chat_owner_constraints"
down_revision: str | None = "0011_document_lifecycle_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM qa_messages AS qm
        WHERE NOT EXISTS (
            SELECT 1
            FROM qa_sessions AS qs
            WHERE qs.session_id = qm.session_id
              AND qs.user_id = qm.user_id
        )
        """
    )
    op.drop_constraint("qa_messages_session_id_fkey", "qa_messages", type_="foreignkey")
    op.create_unique_constraint(
        "uq_qa_sessions_session_user",
        "qa_sessions",
        ["session_id", "user_id"],
    )
    op.create_foreign_key(
        "fk_qa_messages_session_user",
        "qa_messages",
        "qa_sessions",
        ["session_id", "user_id"],
        ["session_id", "user_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_qa_messages_session_user", "qa_messages", type_="foreignkey")
    op.drop_constraint("uq_qa_sessions_session_user", "qa_sessions", type_="unique")
    op.create_foreign_key(
        "qa_messages_session_id_fkey",
        "qa_messages",
        "qa_sessions",
        ["session_id"],
        ["session_id"],
        ondelete="CASCADE",
    )
