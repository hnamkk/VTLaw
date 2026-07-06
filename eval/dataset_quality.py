"""Static quality checks that keep the golden set broad and auditable."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from eval.schemas import EvalCase

_CITATION_REQUIRED_BEHAVIORS = {
    "answer_with_citations",
    "answer_with_multiple_citations",
}
_ANSWER_BEHAVIORS = _CITATION_REQUIRED_BEHAVIORS | {"answer_with_document_sources"}
_SAFE_NEGATIVE_BEHAVIORS = {
    "clarification_needed",
    "deflect",
    "deflect_or_refuse_guardrail_bypass",
    "insufficient_context",
    "multiple_possibilities",
}


def _normalize_question(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\W+", " ", value).strip()


def dataset_quality_issues(cases: list[EvalCase]) -> list[str]:
    """Return deterministic dataset defects; an empty list means publishable."""
    issues: list[str] = []
    if len(cases) < 24:
        issues.append("dataset_too_small")

    ids = Counter(case.case_id for case in cases)
    questions = Counter(_normalize_question(case.question) for case in cases)
    if any(
        not case.case_id or not case.category or not case.question for case in cases
    ):
        issues.append("missing_required_field")
    if any(count > 1 for count in ids.values()):
        issues.append("duplicate_case_id")
    if any(question and count > 1 for question, count in questions.items()):
        issues.append("duplicate_question")

    answerable = [case for case in cases if case.expected_behavior in _ANSWER_BEHAVIORS]
    negative = [
        case for case in cases if case.expected_behavior in _SAFE_NEGATIVE_BEHAVIORS
    ]
    if len(answerable) < 12:
        issues.append("insufficient_answerable_coverage")
    if len(negative) / max(len(cases), 1) < 0.30:
        issues.append("insufficient_negative_coverage")

    for case in answerable:
        if (
            not case.expected_doc_ids
            and not case.acceptable_doc_ids
            or not case.expected_answer_points
        ):
            issues.append(f"{case.case_id}:ungrounded_answerable_case")
        if case.expected_behavior in _CITATION_REQUIRED_BEHAVIORS and case.min_citations < 1:
            issues.append(f"{case.case_id}:missing_citation_requirement")

    for case in negative:
        if case.expected_doc_ids or case.expected_answer_points:
            issues.append(f"{case.case_id}:negative_case_has_expected_answer")
        if not case.must_have_no_citations:
            issues.append(f"{case.case_id}:negative_case_allows_citations")

    required_categories = {
        "active_law_qa",
        "citation_accuracy",
        "insufficient_context",
        "out_of_scope",
        "prompt_injection",
        "temporal_boundary",
    }
    categories = {case.category for case in cases}
    missing_categories = sorted(required_categories - categories)
    if missing_categories:
        issues.append(f"missing_categories:{','.join(missing_categories)}")

    required_tags = {
        "definition",
        "procedure",
        "threshold",
        "temporal",
        "ambiguity",
        "insufficient_evidence",
        "out_of_scope",
        "prompt_injection",
    }
    tags = {tag for case in cases for tag in case.tags}
    missing_tags = sorted(required_tags - tags)
    if missing_tags:
        issues.append(f"missing_tags:{','.join(missing_tags)}")

    references = [
        doc
        for case in answerable
        for doc in case.expected_doc_ids + case.acceptable_doc_ids
    ]
    if references:
        top_count = Counter(references).most_common(1)[0][1]
        if top_count / len(references) > 0.35:
            issues.append("expected_source_concentration")

    if sum(case.category == "prompt_injection" for case in cases) < 3:
        issues.append("insufficient_prompt_injection_coverage")
    if sum(case.category == "insufficient_context" for case in cases) < 4:
        issues.append("insufficient_abstention_coverage")
    return issues
