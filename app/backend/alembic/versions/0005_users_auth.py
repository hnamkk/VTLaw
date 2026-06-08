"""add users auth table

Revision ID: 0005_users_auth
Revises: 0004_unique_source_checksum
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_users_auth"
down_revision: Union[str, None] = "0004_unique_source_checksum"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=10), server_default="USER", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('USER', 'ADMIN')", name="ck_users_role"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("idx_users_role", "users", ["role"])
    op.create_index("idx_users_is_active", "users", ["is_active"])
    op.create_index(
        "uq_users_username_lower",
        "users",
        [sa.text("lower(username)")],
        unique=True,
        postgresql_where=sa.text("username IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_users_is_active", table_name="users")
    op.drop_index("uq_users_username_lower", table_name="users")
    op.drop_index("idx_users_role", table_name="users")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")
