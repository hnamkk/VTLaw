from __future__ import annotations

from types import SimpleNamespace

from src.core.observability import redact_pii
from src.quality.service import _pipeline_metadata, issue_specs_from_result


def _citation(status: str) -> SimpleNamespace:
    return SimpleNamespace(verification_status=SimpleNamespace(value=status))


def test_redact_pii_masks_email_and_vietnamese_phone_number():
    value = redact_pii("Lien he an.nguyen@example.vn hoac 0912 345 678")

    assert value == "Lien he [EMAIL_REDACTED] hoac [PHONE_REDACTED]"


def test_critical_domain_violations_create_actionable_issues():
    issues = issue_specs_from_result(
        active_filter_violation=True,
        disclaimer_missing=True,
        has_hallucination=True,
        low_confidence=False,
        citations=[_citation("blocked")],
    )

    assert {(issue.issue_type, issue.severity) for issue in issues} == {
        ("active_filter_violation", "critical"),
        ("disclaimer_missing", "critical"),
        ("unsupported_claim", "critical"),
    }


def test_weak_citation_and_safe_abstention_are_review_issues_not_blockers():
    issues = issue_specs_from_result(
        active_filter_violation=False,
        disclaimer_missing=False,
        has_hallucination=False,
        low_confidence=True,
        citations=[_citation("partial")],
    )

    assert [(issue.issue_type, issue.severity) for issue in issues] == [
        ("citation_verification", "high"),
        ("low_confidence", "medium"),
    ]


def test_verified_response_creates_no_issue():
    issues = issue_specs_from_result(
        active_filter_violation=False,
        disclaimer_missing=False,
        has_hallucination=False,
        low_confidence=False,
        citations=[_citation("verified")],
    )

    assert issues == []


def test_pipeline_metadata_explains_runtime_versions_and_stages():
    values = {
        "scope_result": SimpleNamespace(label=SimpleNamespace(value="in_scope"), score=0.91),
        "status_filter": "active",
        "retrieval_candidate_count": 24,
        "reranker_used": True,
        "reranker_failed": False,
        "reranker_error_code": None,
        "rerank_top_score": 0.87,
        "faithfulness_score": 0.94,
        "has_hallucination": False,
    }

    metadata = _pipeline_metadata(values, [{"citation_id": "cit-1"}], [object(), object()])

    assert metadata["versions"]["prompt"] == "legal-rag-v2"
    assert metadata["versions"]["ranking_model"] == "legal-rank-v2"
    assert metadata["scope"] == {"label": "in_scope", "score": 0.91}
    assert metadata["retrieval"] == {
        "status_filter": "active",
        "candidate_count": 24,
        "context_count": 2,
    }
    assert metadata["ranking"]["top_score"] == 0.87
    assert metadata["verification"]["citation_count"] == 1
