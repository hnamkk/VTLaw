"""Operational AI-quality observations, issues, and release checks."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class QualityObservation(Base):
    __tablename__ = "quality_observations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'cancelled')",
            name="ck_quality_observations_status",
        ),
        Index("idx_quality_observations_created", "created_at"),
        Index("idx_quality_observations_status", "status"),
        Index("idx_quality_observations_faithfulness", "faithfulness_score"),
    )

    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="started")
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default="[]")
    evidence: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default="[]")
    pipeline_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_out_of_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    has_hallucination: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active_filter_violation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    disclaimer_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    guardrail_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guardrail_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_token_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_tracing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QualityIssue(Base):
    __tablename__ = "quality_issues"
    __table_args__ = (
        CheckConstraint(
            "issue_type IN ('active_filter_violation', 'disclaimer_missing', "
            "'unsupported_claim', 'citation_verification', 'low_confidence', "
            "'chat_error', 'user_report')",
            name="ck_quality_issues_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_quality_issues_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'reviewing', 'resolved', 'dismissed')",
            name="ck_quality_issues_status",
        ),
        Index("idx_quality_issues_status_severity", "status", "severity", "created_at"),
        Index("idx_quality_issues_trace", "trace_id"),
    )

    issue_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    trace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("quality_observations.trace_id", ondelete="CASCADE"),
        nullable=False,
    )
    issue_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    machine_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reviewer_conclusion: Mapped[str | None] = mapped_column(String(40), nullable=True)
    root_cause: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QualityReleaseCheck(Base):
    __tablename__ = "quality_release_checks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('passed', 'failed', 'invalid')",
            name="ck_quality_release_checks_status",
        ),
        Index("idx_quality_release_checks_generated", "generated_at"),
        Index("idx_quality_release_checks_status", "status"),
    )

    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(80), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    invalid_cases: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    evaluator_errors: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    gate_failures: Mapped[list[str]] = mapped_column(
        ARRAY(String()), nullable=False, server_default="{}"
    )
    generated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualityReleaseCase(Base):
    __tablename__ = "quality_release_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('passed', 'failed', 'skipped', 'invalid')",
            name="ck_quality_release_cases_status",
        ),
        Index("idx_quality_release_cases_run_status", "run_id", "status"),
    )

    result_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("quality_release_checks.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")


__all__ = [
    "QualityIssue",
    "QualityObservation",
    "QualityReleaseCase",
    "QualityReleaseCheck",
]
