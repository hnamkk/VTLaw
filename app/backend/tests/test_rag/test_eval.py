"""Tests for the golden dataset and strict release-gate contract."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import eval.run_eval as run_eval_module
from eval.dataset import load_by_category, load_cases
from eval.dataset_quality import dataset_quality_issues
from eval.metrics import (
    compute_deflection_rate,
    compute_hallucination_rate,
    evaluation_status,
    passes_release_gate,
    percentile_10,
    percentile_95,
    release_gate_failures,
    release_gate_warnings,
)
from eval.run_eval import (
    ExpectedDoc,
    build_expected_doc_map,
    build_initial_agent_state,
    build_report,
    citation_expectation_satisfied,
    deterministic_behavior_failures,
    metadata_contract_failures,
    non_active_document_ids,
    select_cases_for_run,
    write_report,
)
from eval.schemas import EvalCase, EvalMetrics


def _passing_metrics(**overrides) -> EvalMetrics:
    metrics = EvalMetrics(
        total_cases=25,
        executed_cases=25,
        valid_cases=25,
        faithfulness=0.94,
        faithfulness_eligible_cases=18,
        faithfulness_sample_size=18,
        faithfulness_min=0.82,
        faithfulness_p10=0.90,
        answer_relevancy=0.88,
        citation_accuracy=0.99,
        citation_correct_cases=20,
        citation_eligible_cases=20,
        hallucination_rate=0.01,
        out_of_scope_deflection=0.96,
        safe_abstention_accuracy=0.96,
        prompt_injection_block_rate=1.0,
        answerable_abstention_rate=0.04,
        false_abstention_rate=0.04,
        answer_mode_accuracy=1.0,
        answer_mode_correct_cases=10,
        answer_mode_eligible_cases=10,
        risk_policy_accuracy=1.0,
        risk_policy_correct_cases=10,
        risk_policy_eligible_cases=10,
        clarification_question_accuracy=1.0,
        clarification_correct_cases=2,
        clarification_eligible_cases=2,
        follow_up_resolution_accuracy=1.0,
        follow_up_correct_cases=2,
        follow_up_eligible_cases=2,
        legal_advice_strategy_block_rate=1.0,
        legal_advice_blocked_cases=1,
        legal_advice_eligible_cases=1,
        historical_reference_isolation_rate=1.0,
        historical_reference_isolated_cases=1,
        historical_reference_isolation_eligible_cases=1,
        required_provision_citation_coverage=1.0,
        required_provision_citation_cases=3,
        provision_citation_eligible_cases=3,
        required_document_source_coverage=1.0,
        required_document_source_cases=2,
        document_source_eligible_cases=2,
        metadata_contract_completeness_rate=1.0,
        metadata_contract_complete_cases=25,
        metadata_contract_eligible_cases=25,
        active_filter_violations=0,
        deterministic_behavior_violations=0,
        disclaimer_missing=0,
        high_risk_unsupported_claims=0,
        p95_latency_ms=4200,
    )
    return replace(metrics, **overrides)


def test_load_cases_reads_all_golden_files():
    cases = load_cases()
    assert len(cases) >= 30
    categories = {c.category for c in cases}
    assert "active_law_qa" in categories
    assert "out_of_scope" in categories
    assert "citation_accuracy" in categories
    assert "temporal_boundary" in categories
    assert "prompt_injection" in categories
    assert any(c.expected_answer_mode for c in cases)
    assert any(c.conversation_context for c in cases)


def test_golden_dataset_has_no_balance_or_grounding_issues():
    assert dataset_quality_issues(load_cases()) == []


def test_load_by_category_filters_correctly():
    cases = load_by_category("out_of_scope")
    assert cases
    assert all(c.category == "out_of_scope" for c in cases)


def test_select_cases_for_run_filters_by_category_and_limit(monkeypatch):
    cases = [
        EvalCase(
            case_id="case-1",
            category="citation_accuracy",
            question="q1",
            expected_behavior="answer_with_citations",
        ),
        EvalCase(
            case_id="case-2",
            category="out_of_scope",
            question="q2",
            expected_behavior="deflect",
        ),
        EvalCase(
            case_id="case-3",
            category="out_of_scope",
            question="q3",
            expected_behavior="deflect",
        ),
    ]
    monkeypatch.setattr(run_eval_module, "EVAL_CASE_IDS", "")
    monkeypatch.setattr(run_eval_module, "EVAL_CATEGORIES", "out_of_scope")
    monkeypatch.setattr(run_eval_module, "EVAL_CASE_OFFSET", "1")
    monkeypatch.setattr(run_eval_module, "EVAL_CASE_LIMIT", "1")

    selected = select_cases_for_run(cases)

    assert [case.case_id for case in selected] == ["case-3"]


def test_percentiles():
    assert percentile_95([100, 200, 300, 400, 500]) == 500
    assert percentile_95([1000]) == 1000
    assert percentile_95([]) == 0
    assert percentile_10([0.95, 0.80, 0.90, 0.85]) == 0.80
    assert percentile_10([]) is None


def test_rate_helpers():
    assert compute_hallucination_rate(1, 20) == 0.05
    assert compute_deflection_rate(9, 10) == 0.9


def test_release_gate_passes_only_with_strict_metrics_and_full_coverage():
    metrics = _passing_metrics()

    assert release_gate_failures(metrics) == []
    assert release_gate_warnings(metrics) == []
    assert evaluation_status(metrics) == "passed"
    assert passes_release_gate(metrics) is True


def test_release_gate_fails_quality_thresholds():
    metrics = _passing_metrics(
        faithfulness=0.89,
        faithfulness_min=0.70,
        answer_relevancy=0.80,
        citation_accuracy=0.95,
        hallucination_rate=0.03,
        out_of_scope_deflection=0.90,
        safe_abstention_accuracy=0.90,
        prompt_injection_block_rate=0.99,
        answerable_abstention_rate=0.10,
        false_abstention_rate=0.11,
        answer_mode_accuracy=0.90,
        risk_policy_accuracy=0.90,
        clarification_question_accuracy=0.80,
        follow_up_resolution_accuracy=0.80,
        legal_advice_strategy_block_rate=0.99,
        historical_reference_isolation_rate=0.99,
        required_provision_citation_coverage=0.99,
        required_document_source_coverage=0.99,
        metadata_contract_completeness_rate=0.99,
        active_filter_violations=1,
        deterministic_behavior_violations=1,
        disclaimer_missing=2,
        high_risk_unsupported_claims=1,
        p95_latency_ms=6000,
    )

    failures = release_gate_failures(metrics)
    assert evaluation_status(metrics) == "failed"
    assert {
        "active_filter_violation",
        "deterministic_behavior_violation",
        "disclaimer_missing",
        "high_risk_unsupported_claim",
        "hallucination_rate",
        "faithfulness",
        "faithfulness_case_floor",
        "out_of_scope_deflection",
        "safe_abstention_accuracy",
        "prompt_injection_block_rate",
        "citation_accuracy",
        "false_abstention",
        "answer_mode_accuracy",
        "risk_policy_accuracy",
        "clarification_question_accuracy",
        "follow_up_resolution_accuracy",
        "legal_advice_strategy_block_rate",
        "historical_reference_isolation",
        "required_provision_citation_coverage",
        "required_document_source_coverage",
        "metadata_contract_completeness",
        "p95_latency",
    }.issubset(failures)
    assert passes_release_gate(metrics) is False


def test_release_gate_warnings_track_non_blocking_quality_targets():
    metrics = _passing_metrics(
        faithfulness=0.91,
        answer_relevancy=0.80,
        answerable_abstention_rate=0.06,
    )

    assert release_gate_failures(metrics) == []
    assert set(release_gate_warnings(metrics)) == {
        "faithfulness_target",
        "answer_relevancy",
        "answerable_abstention",
    }
    assert passes_release_gate(metrics) is True


def test_release_gate_is_invalid_when_cases_are_skipped():
    metrics = _passing_metrics(
        executed_cases=24,
        valid_cases=24,
        skipped_cases=1,
    )

    assert evaluation_status(metrics) == "invalid"
    assert "execution_coverage" in release_gate_failures(metrics)
    assert passes_release_gate(metrics) is False


def test_missing_faithfulness_never_becomes_a_passing_score():
    metrics = _passing_metrics(
        faithfulness=None,
        faithfulness_sample_size=17,
        invalid_cases=1,
    )

    failures = release_gate_failures(metrics)
    assert evaluation_status(metrics) == "invalid"
    assert "faithfulness_coverage" in failures
    assert "invalid_cases" in failures
    assert passes_release_gate(metrics) is False


def test_run_eval_writes_invalid_report_with_diagnostics(tmp_path, monkeypatch):
    report_path = tmp_path / "latest_rag_eval.md"
    monkeypatch.setattr(run_eval_module, "REPORT_PATH", report_path)
    metrics = _passing_metrics(
        executed_cases=24,
        valid_cases=24,
        skipped_cases=1,
    )
    report = build_report(metrics, skipped_cases=["case-x: doc-nd336-2025:missing"])

    write_report(report)

    assert report.status == "invalid"
    assert report.pass_release_gate is False
    text = report_path.read_text(encoding="utf-8")
    assert "Evaluation status: invalid" in text
    assert "Executed cases: 24" in text
    assert "Skipped Cases" in text


def test_number_alias_resolves_without_inferred_document_type():
    document = SimpleNamespace(
        doc_id="doc-1",
        document_number="02/VBHN-BGTVT",
        title="Văn bản hợp nhất",
        doc_type="CONG_VAN",
        status="active",
    )

    resolved = build_expected_doc_map([document], {"number:02/VBHN-BGTVT"})

    assert resolved["number:02/VBHN-BGTVT"].doc_id == "doc-1"


def test_eval_runner_uses_current_kb_v2_document_model_only():
    assert hasattr(run_eval_module, "KbV2LegalDocument")
    assert not hasattr(run_eval_module, "LegalDocument")


def test_eval_runner_initial_state_matches_chat_api_contract():
    state = build_initial_agent_state("Con nop o dau?", "Truoc do hoi ve dang ky xe.")

    assert state["query_intent"] is None
    assert state["query_has_explicit_date"] is False
    assert state["conversation_context"] == "Truoc do hoi ve dang ky xe."
    assert state["response_document_sources"] == []
    assert state["response_historical_references"] == []
    assert state["guardrail_reason"] is None
    assert state["injection_detected"] is None


def test_citation_expectation_accepts_one_grounded_alternative():
    case = EvalCase(
        case_id="alternatives",
        category="active_law_qa",
        question="question",
        expected_behavior="answer_with_citations",
        acceptable_doc_ids=["number:41/VBHN-BCA", "number:55/VBHN-VPQH"],
    )
    doc_map = {
        alias: ExpectedDoc(
            alias=alias,
            doc_id=doc_id,
            status="active",
            document_number=alias.removeprefix("number:"),
            title=alias,
        )
        for alias, doc_id in (
            ("number:41/VBHN-BCA", "doc-41"),
            ("number:55/VBHN-VPQH", "doc-55"),
        )
    }

    assert citation_expectation_satisfied(case, doc_map, {"doc-55"}) is True
    assert citation_expectation_satisfied(case, doc_map, {"other"}) is False


def test_non_active_retrieval_is_a_violation_before_citation():
    chunks = [
        SimpleNamespace(doc_id="active", status="active"),
        SimpleNamespace(doc_id="future", status="pending_review"),
        SimpleNamespace(doc_id="", status=""),
    ]

    assert non_active_document_ids(chunks) == {"future"}


def test_deterministic_behavior_checks_safe_abstention_and_forbidden_sources():
    case = EvalCase(
        case_id="temporal",
        category="temporal_boundary",
        question="question",
        expected_behavior="insufficient_context",
        forbidden_doc_ids=["number:94/2026/ND-CP"],
        accepted_guardrail_reasons=["low_confidence_retrieval"],
        must_have_no_citations=True,
    )
    doc_map = {
        "number:94/2026/ND-CP": ExpectedDoc(
            alias="number:94/2026/ND-CP",
            doc_id="future-doc",
            status="pending_review",
            document_number="94/2026/ND-CP",
            title="Nghị định 94",
        )
    }
    unsafe = {
        "guardrail_reason": None,
        "retrieved_contexts": [SimpleNamespace(doc_id="future-doc")],
        "verified_citations": [
            SimpleNamespace(doc_id="future-doc"),
            SimpleNamespace(doc_id=""),
        ],
    }
    unsafe_metadata = {
        "answer_mode": "direct",
        "provision_citations": [],
        "document_sources": [],
        "historical_references": [],
        "clarification_question": None,
    }
    safe = {
        "guardrail_reason": "low_confidence_retrieval",
        "verified_citations": [],
    }
    safe_metadata = {
        "answer_mode": "insufficient_evidence",
        "provision_citations": [],
        "document_sources": [],
        "historical_references": [],
        "clarification_question": None,
    }

    assert set(deterministic_behavior_failures(case, unsafe, unsafe_metadata, doc_map)) == {
        "unexpected_citation",
        "forbidden_document_cited",
        "forbidden_document_retrieved",
        "expected_guardrail_missing",
        "invalid_citation_identity",
    }
    assert deterministic_behavior_failures(case, safe, safe_metadata, doc_map) == []


def test_dataset_quality_rejects_concentration_and_duplicates():
    base = EvalCase(
        case_id="same",
        category="active_law_qa",
        question="Cùng một câu hỏi",
        expected_behavior="answer_with_citations",
        expected_doc_ids=["number:one"],
        expected_answer_points=["point"],
        tags=["definition"],
        min_citations=1,
    )

    issues = dataset_quality_issues([base] * 24)

    assert "duplicate_case_id" in issues
    assert "duplicate_question" in issues
    assert "expected_source_concentration" in issues


def test_deterministic_behavior_checks_answer_mode_and_metadata_requirements():
    case = EvalCase(
        case_id="meta-check",
        category="multi_document",
        question="question",
        expected_behavior="multiple_possibilities",
        expected_answer_mode="multiple_possibilities",
        expected_risk_level="medium",
        accepted_guardrail_reasons=["evidence_multiple_possibilities"],
        min_document_sources=2,
        min_historical_references=1,
        require_clarification_question=True,
        min_provision_citations=1,
    )
    result = {
        "guardrail_reason": "evidence_multiple_possibilities",
        "retrieved_contexts": [],
        "verified_citations": [],
    }
    bad_metadata = {
        "answer_mode": "direct",
        "risk_level": "low",
        "confidence": "high",
        "provision_citations": [],
        "document_sources": [{"document_id": "doc-1"}],
        "historical_references": [],
        "clarification_question": None,
    }

    assert set(deterministic_behavior_failures(case, result, bad_metadata, {})) == {
        "unexpected_answer_mode",
        "unexpected_risk_level",
        "minimum_provision_citations",
        "minimum_document_sources",
        "minimum_historical_references",
        "missing_clarification_question",
    }


def test_metadata_contract_rejects_mixed_historical_and_current_citations():
    case = EvalCase(
        case_id="historical-contract",
        category="temporal_boundary",
        question="question",
        expected_behavior="historical_answer",
        min_historical_references=1,
    )
    bad_metadata = {
        "answer_mode": "historical",
        "risk_level": "medium",
        "confidence": "medium",
        "provision_citations": [
            {"document_id": "doc-old", "effective_status": "expired"}
        ],
        "historical_references": [{"document_id": "doc-old"}],
        "document_sources": [],
    }

    assert set(metadata_contract_failures(case, bad_metadata)) == {
        "non_active_provision_citation",
        "historical_reference_in_provision_citations",
    }
