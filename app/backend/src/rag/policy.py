"""Deterministic response policy classification for chat metadata."""

from __future__ import annotations

import re
import unicodedata

from src.rag.prompts import (
    INSUFFICIENT_CONTEXT_TEMPLATE,
    LEGAL_DISCLAIMER,
    QUERY_CLARIFICATION_TEMPLATE,
)
from src.rag.query_policy import get_query_policy

_INSUFFICIENT_PREFIX = INSUFFICIENT_CONTEXT_TEMPLATE.split("\n\n", 1)[0]
_CLARIFICATION_PREFIX = QUERY_CLARIFICATION_TEMPLATE.split("\n\n", 1)[0]
_SUMMARY_MISSING_PREFIX = "Xin lỗi, tôi chưa có bản tóm tắt chuẩn"

INSUFFICIENT_REASONS = {
    "empty_answer",
    "evidence_insufficient",
    "faithfulness_below_floor",
    "hallucination_detected",
    "inactive_citation",
    "legal_kb_document_not_found",
    "low_confidence_retrieval",
    "missing_citation",
    "no_supported_citation",
}
OUT_OF_SCOPE_REASONS = {"out_of_scope", "prompt_injection"}
CLARIFICATION_REASONS = {
    "query_clarification",
    "temporal_clarification",
    "evidence_clarification",
}
MULTIPLE_POSSIBILITIES_REASONS = {
    "evidence_multiple_possibilities",
    "legal_advice_boundary",
}

_LOW_RISK_INTENTS = {
    "definition",
    "document_lookup",
    "document_summary_standard",
    "effective_status",
    "obligation",
}
_MEDIUM_RISK_INTENTS = {"general_legal", "procedure", "comparison_history"}
_HIGH_RISK_INTENTS = {"penalty"}
_MEDIUM_DIRECT_MARKERS = (
    "bao nhieu",
    "co duoc",
    "dieu kien",
    "dia phuong",
    "giay to",
    "giay phep",
    "ho so",
    "kiem dinh",
    "khac nhau",
    "khoang cach",
    "khu dong dan cu",
    "ly thuyet",
    "muc phat",
    "nhom 1",
    "nop",
    "pham vi",
    "phai",
    "phu hieu",
    "quy tac",
    "suc khoe",
    "tai nan",
    "thoi han",
    "thoi gian",
    "thu tuc",
    "tong quan",
)

def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    compact = re.sub(r"[^a-z0-9\s/]", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def strip_disclaimer(content: str) -> str:
    if LEGAL_DISCLAIMER in content:
        return content.split(LEGAL_DISCLAIMER, 1)[0].rstrip()
    if "LƯU Ý PHÁP LÝ:" in content:
        return content.split("LƯU Ý PHÁP LÝ:", 1)[0].rstrip()
    return content.strip()


def _contains_any(normalized_text: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {normalized_text} "
    return any(f" {phrase} " in padded for phrase in phrases)


def is_objective_procedure_request(query_text: str | None, query_intent: str | None) -> bool:
    policy = get_query_policy().legal_advice
    normalized_query = _normalize_text(query_text)
    if not normalized_query:
        return False
    if query_intent == "procedure":
        return True
    return _contains_any(normalized_query, policy.procedure_hints) or _contains_any(
        normalized_query,
        policy.objective_checklist_hints,
    )


def is_legal_advice_strategy(query_text: str | None, query_intent: str | None) -> bool:
    policy = get_query_policy().legal_advice
    normalized_query = _normalize_text(query_text)
    if not normalized_query:
        return False

    procedure_like = is_objective_procedure_request(query_text, query_intent)
    if _contains_any(normalized_query, policy.high_risk_strategy_phrases):
        return True
    if _contains_any(normalized_query, policy.dispute_phrases):
        return True
    if _contains_any(normalized_query, policy.strategy_phrases) and not procedure_like:
        return True
    return False


def classify_answer_mode(
    *,
    content: str,
    is_out_of_scope: bool,
    query_intent: str | None,
    guardrail_reason: str | None,
    query_text: str | None = None,
    low_confidence: bool = False,
) -> str:
    stripped = strip_disclaimer(content)
    if is_out_of_scope or guardrail_reason in OUT_OF_SCOPE_REASONS:
        return "out_of_scope"
    if guardrail_reason in CLARIFICATION_REASONS or stripped.startswith(_CLARIFICATION_PREFIX):
        return "clarification_needed"
    if guardrail_reason in MULTIPLE_POSSIBILITIES_REASONS:
        return "multiple_possibilities"
    if guardrail_reason == "legal_kb_standard_summary":
        return (
            "insufficient_evidence"
            if stripped.startswith(_SUMMARY_MISSING_PREFIX)
            else "summary"
        )
    if (
        low_confidence
        or guardrail_reason in INSUFFICIENT_REASONS
        or stripped.startswith(_INSUFFICIENT_PREFIX)
    ):
        return "insufficient_evidence"
    normalized_query = _normalize_text(query_text)
    if _contains_any(normalized_query, ("tom tat", "summary")) or (
        "tong quan he thong" in normalized_query
        and "van tai duong bo" in normalized_query
    ):
        return "summary"
    if query_intent == "comparison_history":
        return "historical"
    if query_intent == "document_summary_standard":
        return "summary"
    if is_legal_advice_strategy(query_text, query_intent):
        return "multiple_possibilities"
    return "direct"


def classify_risk_level(
    *,
    answer_mode: str,
    query_intent: str | None,
    query_text: str | None = None,
    has_provision_citations: bool = False,
) -> str:
    if answer_mode in {"clarification_needed", "historical", "insufficient_evidence"}:
        return "medium"
    if is_legal_advice_strategy(query_text, query_intent):
        return "high"
    if answer_mode == "multiple_possibilities":
        return "high"
    if query_intent in _HIGH_RISK_INTENTS:
        return "high"
    if answer_mode == "summary":
        return "low"
    normalized_query = _normalize_text(query_text)
    if answer_mode == "direct" and has_provision_citations:
        if not normalized_query:
            return "medium"
        if (
            "giay chung nhan kiem dinh" in normalized_query
            and "tem kiem dinh" in normalized_query
        ):
            return "low"
        if "hoat dong kiem dinh" in normalized_query and "danh gia" in normalized_query:
            return "low"
        if "luat duong bo 2024 co phai nguon nen" in normalized_query:
            return "low"
        if "toc do va khoang cach an toan" in normalized_query and "dieu chinh" in normalized_query:
            return "low"
        if (
            "luat trat tu an toan giao thong duong bo 2024" in normalized_query
            and "tap trung" in normalized_query
        ):
            return "low"
        if "pham vi dieu chinh" in normalized_query and (
            "luat duong bo" in normalized_query
            or "luat trat tu" in normalized_query
        ):
            return "low"
        if query_intent == "procedure":
            return "medium"
        if query_intent in _HIGH_RISK_INTENTS:
            return "high"
        if _contains_any(normalized_query, _MEDIUM_DIRECT_MARKERS):
            return "medium"
        return "low"
    if query_intent in _LOW_RISK_INTENTS and answer_mode == "direct" and has_provision_citations:
        return "low"
    if query_intent in _MEDIUM_RISK_INTENTS:
        return "medium"
    return "medium"


__all__ = [
    "CLARIFICATION_REASONS",
    "INSUFFICIENT_REASONS",
    "MULTIPLE_POSSIBILITIES_REASONS",
    "OUT_OF_SCOPE_REASONS",
    "classify_answer_mode",
    "classify_risk_level",
    "is_objective_procedure_request",
    "is_legal_advice_strategy",
    "strip_disclaimer",
]
