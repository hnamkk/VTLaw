"""Typed schemas for eval dataset and report outputs (spec 14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class EvalCase:
    case_id: str
    category: str
    question: str
    expected_behavior: str
    conversation_context: str = ""
    expected_doc_ids: list[str] = field(default_factory=list)
    acceptable_doc_ids: list[str] = field(default_factory=list)
    expected_chunk_ids: list[str] = field(default_factory=list)
    expected_answer_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    forbidden_doc_ids: list[str] = field(default_factory=list)
    accepted_guardrail_reasons: list[str] = field(default_factory=list)
    expected_answer_mode: str | None = None
    accepted_answer_modes: list[str] = field(default_factory=list)
    expected_risk_level: str | None = None
    accepted_risk_levels: list[str] = field(default_factory=list)
    min_citations: int = 0
    min_provision_citations: int = 0
    min_document_sources: int = 0
    min_historical_references: int = 0
    require_clarification_question: bool = False
    must_have_no_citations: bool = False
    must_include_disclaimer: bool = True
    must_deflect: bool = False
    notes: str = ""


@dataclass(slots=True)
class EvalMetrics:
    total_cases: int
    executed_cases: int
    valid_cases: int
    faithfulness: float | None
    faithfulness_eligible_cases: int
    faithfulness_sample_size: int
    faithfulness_min: float | None
    faithfulness_p10: float | None
    answer_relevancy: float | None
    citation_accuracy: float | None
    citation_correct_cases: int
    citation_eligible_cases: int
    hallucination_rate: float | None
    out_of_scope_deflection: float | None
    safe_abstention_accuracy: float | None
    prompt_injection_block_rate: float | None
    answerable_abstention_rate: float | None
    false_abstention_rate: float | None
    answer_mode_accuracy: float | None
    answer_mode_correct_cases: int
    answer_mode_eligible_cases: int
    risk_policy_accuracy: float | None
    risk_policy_correct_cases: int
    risk_policy_eligible_cases: int
    clarification_question_accuracy: float | None
    clarification_correct_cases: int
    clarification_eligible_cases: int
    follow_up_resolution_accuracy: float | None
    follow_up_correct_cases: int
    follow_up_eligible_cases: int
    legal_advice_strategy_block_rate: float | None
    legal_advice_blocked_cases: int
    legal_advice_eligible_cases: int
    historical_reference_isolation_rate: float | None
    historical_reference_isolated_cases: int
    historical_reference_isolation_eligible_cases: int
    required_provision_citation_coverage: float | None
    required_provision_citation_cases: int
    provision_citation_eligible_cases: int
    required_document_source_coverage: float | None
    required_document_source_cases: int
    document_source_eligible_cases: int
    metadata_contract_completeness_rate: float | None
    metadata_contract_complete_cases: int
    metadata_contract_eligible_cases: int
    active_filter_violations: int
    deterministic_behavior_violations: int
    disclaimer_missing: int
    high_risk_unsupported_claims: int
    p95_latency_ms: int
    skipped_cases: int = 0
    invalid_cases: int = 0
    evaluator_errors: int = 0


@dataclass(slots=True)
class EvalReport:
    dataset_files: list[Path]
    metrics: EvalMetrics
    status: str
    pass_release_gate: bool
    gate_failures: list[str] = field(default_factory=list)
    gate_warnings: list[str] = field(default_factory=list)
    skipped_cases: list[str] = field(default_factory=list)
    invalid_cases: list[str] = field(default_factory=list)
    evaluator_errors: list[str] = field(default_factory=list)
    case_results: list[dict] = field(default_factory=list)
