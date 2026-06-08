"""Add actionable runtime evidence to quality observations.

Revision ID: 0008_quality_evidence
Revises: 0007_ai_quality_operations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_quality_evidence"
down_revision: str | None = "0007_ai_quality_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quality_observations",
        sa.Column(
            "pipeline_metadata",
            postgresql.JSONB(),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "quality_observations",
        sa.Column("first_token_latency_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("quality_observations", "first_token_latency_ms")
    op.drop_column("quality_observations", "pipeline_metadata")
