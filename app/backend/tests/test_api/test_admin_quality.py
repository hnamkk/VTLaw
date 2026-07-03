from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api.v1.admin_quality import _release_summary, build_quality_verdict
from src.main import app

client = TestClient(app)


def test_quality_overview_requires_admin_token():
    response = client.get("/api/v1/admin/quality/overview")

    assert response.status_code == 401


def test_quality_verdict_blocks_on_critical_issue():
    verdict = build_quality_verdict(
        critical_issues=2,
        review_issues=4,
        release_status="passed",
        data_status="complete",
    )

    assert verdict.status == "blocked"
    assert "2" in verdict.reason


def test_quality_verdict_is_unknown_without_valid_coverage():
    verdict = build_quality_verdict(
        critical_issues=0,
        review_issues=0,
        release_status="passed",
        data_status="partial",
    )

    assert verdict.status == "unknown"
    assert "dữ liệu" in verdict.title.lower()


def test_quality_verdict_needs_attention_for_review_queue():
    verdict = build_quality_verdict(
        critical_issues=0,
        review_issues=7,
        release_status="passed",
        data_status="complete",
    )

    assert verdict.status == "needs_attention"
    assert "7" in verdict.reason


def test_quality_verdict_is_healthy_only_when_all_inputs_are_ready():
    verdict = build_quality_verdict(
        critical_issues=0,
        review_issues=0,
        release_status="passed",
        data_status="complete",
    )

    assert verdict.status == "healthy"


def test_release_summary_keeps_coverage_and_metric_denominators():
    check = SimpleNamespace(
        run_id="run-1",
        status="invalid",
        dataset_version="dataset-1",
        executed_cases=15,
        total_cases=34,
        valid_cases=14,
        skipped_cases=19,
        invalid_cases=1,
        evaluator_errors=0,
        metrics={
            "faithfulness": 0.91,
            "faithfulness_sample_size": 14,
            "faithfulness_eligible_cases": 15,
            "faithfulness_min": 0.72,
            "faithfulness_p10": 0.80,
            "citation_accuracy": 0.98,
            "citation_correct_cases": 49,
            "citation_eligible_cases": 50,
        },
        gate_failures=["execution_coverage"],
        generated_at=datetime.now(UTC),
    )

    summary = _release_summary(check)

    assert summary.execution_coverage == 15 / 34
    assert (summary.skipped, summary.invalid, summary.evaluator_errors) == (19, 1, 0)
    assert summary.faithfulness.p10 == 0.80
    assert (summary.citation_accuracy.numerator, summary.citation_accuracy.denominator) == (
        49,
        50,
    )
