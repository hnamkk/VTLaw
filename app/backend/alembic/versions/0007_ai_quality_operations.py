"""Add operational AI quality observations, issues, and release checks.

Revision ID: 0007_ai_quality_operations
Revises: 0006_chat_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_ai_quality_operations"
down_revision: str | None = "0006_chat_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quality_observations",
        sa.Column("trace_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), server_default="started", nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("citations", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("is_out_of_scope", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("low_confidence", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("has_hallucination", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "active_filter_violation", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("disclaimer_missing", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("guardrail_stage", sa.String(32), nullable=True),
        sa.Column("guardrail_reason", sa.String(80), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "external_tracing_enabled", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'cancelled')",
            name="ck_quality_observations_status",
        ),
    )
    op.create_index("idx_quality_observations_created", "quality_observations", ["created_at"])
    op.create_index("idx_quality_observations_status", "quality_observations", ["status"])
    op.create_index(
        "idx_quality_observations_faithfulness",
        "quality_observations",
        ["faithfulness_score"],
    )

    op.create_table(
        "quality_issues",
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "trace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("quality_observations.trace_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issue_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("machine_reason", sa.String(120), nullable=True),
        sa.Column("affected_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("reviewer_conclusion", sa.String(40), nullable=True),
        sa.Column("root_cause", sa.String(80), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "issue_type IN ('active_filter_violation', 'disclaimer_missing', "
            "'unsupported_claim', 'citation_verification', 'low_confidence', "
            "'chat_error', 'user_report')",
            name="ck_quality_issues_type",
        ),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_quality_issues_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'reviewing', 'resolved', 'dismissed')",
            name="ck_quality_issues_status",
        ),
    )
    op.create_index(
        "idx_quality_issues_status_severity",
        "quality_issues",
        ["status", "severity", "created_at"],
    )
    op.create_index("idx_quality_issues_trace", "quality_issues", ["trace_id"])

    op.create_table(
        "quality_release_checks",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("dataset_version", sa.String(80), nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("executed_cases", sa.Integer(), nullable=False),
        sa.Column("valid_cases", sa.Integer(), nullable=False),
        sa.Column("skipped_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("invalid_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evaluator_errors", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "gate_failures", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'invalid')",
            name="ck_quality_release_checks_status",
        ),
    )
    op.create_index(
        "idx_quality_release_checks_generated", "quality_release_checks", ["generated_at"]
    )
    op.create_index(
        "idx_quality_release_checks_status", "quality_release_checks", ["status"]
    )

    op.create_table(
        "quality_release_cases",
        sa.Column(
            "result_id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.func.gen_random_uuid(),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("quality_release_checks.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(80), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("answer_relevancy", sa.Float(), nullable=True),
        sa.Column("details", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "status IN ('passed', 'failed', 'skipped', 'invalid')",
            name="ck_quality_release_cases_status",
        ),
    )
    op.create_index(
        "idx_quality_release_cases_run_status",
        "quality_release_cases",
        ["run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_quality_release_cases_run_status", table_name="quality_release_cases")
    op.drop_table("quality_release_cases")
    op.drop_index("idx_quality_release_checks_status", table_name="quality_release_checks")
    op.drop_index("idx_quality_release_checks_generated", table_name="quality_release_checks")
    op.drop_table("quality_release_checks")
    op.drop_index("idx_quality_issues_trace", table_name="quality_issues")
    op.drop_index("idx_quality_issues_status_severity", table_name="quality_issues")
    op.drop_table("quality_issues")
    op.drop_index("idx_quality_observations_faithfulness", table_name="quality_observations")
    op.drop_index("idx_quality_observations_status", table_name="quality_observations")
    op.drop_index("idx_quality_observations_created", table_name="quality_observations")
    op.drop_table("quality_observations")
