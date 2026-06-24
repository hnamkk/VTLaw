"""Response contracts for the admin AI-quality workbench."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QualityVerdict(BaseModel):
    status: Literal["blocked", "needs_attention", "healthy", "unknown"]
    title: str
    reason: str
    next_action: str


class TraceCoverage(BaseModel):
    traced: int
    total: int
    rate: float


class QualityDataStatus(BaseModel):
    status: Literal["complete", "partial", "empty"]
    production_trace_coverage: TraceCoverage
    blind_spots: list[str] = Field(default_factory=list)


class QualityBlockers(BaseModel):
    open: int
    active_filter_violations: int
    disclaimer_missing: int
    high_risk_unsupported_claims: int


class ReleaseMetric(BaseModel):
    value: float | None = None
    threshold: float
    sample_size: int | None = None
    eligible_count: int | None = None
    minimum: float | None = None
    p10: float | None = None
    numerator: int | None = None
    denominator: int | None = None


class ReleaseCheckSummary(BaseModel):
    run_id: str
    status: Literal["passed", "failed", "invalid"]
    dataset_version: str
    executed: int
    required: int
    valid: int
    skipped: int
    invalid: int
    evaluator_errors: int
    execution_coverage: float
    faithfulness: ReleaseMetric
    citation_accuracy: ReleaseMetric
    gate_failures: list[str] = Field(default_factory=list)
    generated_at: datetime


class QualityActionQueue(BaseModel):
    critical: int
    needs_review: int
    oldest_opened_at: datetime | None = None


class ProductionQualitySummary(BaseModel):
    total_requests: int
    completed_requests: int
    evaluated_responses: int
    average_faithfulness: float | None = None
    abstained_responses: int
    failed_requests: int
    p95_latency_ms: int | None = None


class QualityOverviewResponse(BaseModel):
    verdict: QualityVerdict
    as_of: datetime
    period_days: int
    data_quality: QualityDataStatus
    blockers: QualityBlockers
    latest_release_check: ReleaseCheckSummary | None = None
    action_queue: QualityActionQueue
    production: ProductionQualitySummary


class QualityIssueItem(BaseModel):
    issue_id: str
    trace_id: str
    issue_type: str
    severity: str
    status: str
    title: str
    summary: str
    machine_reason: str | None = None
    affected_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    next_action: str
    created_at: datetime
    updated_at: datetime


class QualityIssueListResponse(BaseModel):
    items: list[QualityIssueItem]
    total: int
    page: int
    page_size: int


class QualityObservationDetail(BaseModel):
    trace_id: str
    session_id: str
    environment: str
    status: str
    query_text: str
    response_text: str | None = None
    citations: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    pipeline_metadata: dict = Field(default_factory=dict)
    faithfulness_score: float | None = None
    is_out_of_scope: bool
    low_confidence: bool
    has_hallucination: bool
    active_filter_violation: bool
    disclaimer_missing: bool
    guardrail_stage: str | None = None
    guardrail_reason: str | None = None
    first_token_latency_ms: int | None = None
    latency_ms: int | None = None
    error_summary: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class QualityIssueDetail(QualityIssueItem):
    evidence: dict = Field(default_factory=dict)
    reviewer_conclusion: str | None = None
    root_cause: str | None = None
    reviewer_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    observation: QualityObservationDetail


class QualityIssueReviewRequest(BaseModel):
    status: Literal["reviewing", "resolved", "dismissed"]
    conclusion: Literal["confirmed", "false_positive", "kb_gap", "retrieval_miss"]
    root_cause: str | None = Field(default=None, max_length=80)
    note: str = Field(min_length=3, max_length=4000)


class ReleaseCheckListResponse(BaseModel):
    items: list[ReleaseCheckSummary]
    total: int
    page: int
    page_size: int


class ReleaseCaseItem(BaseModel):
    case_id: str
    category: str
    status: str
    faithfulness_score: float | None = None
    answer_relevancy: float | None = None
    details: dict = Field(default_factory=dict)


class ReleaseCheckDetail(ReleaseCheckSummary):
    config: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    cases: list[ReleaseCaseItem] = Field(default_factory=list)
