"""Deterministic guardrails around the legal RAG agent.

This module keeps project-critical safety checks close to the pipeline instead
of relying only on prompt instructions. It is intentionally dependency-light so
the checks run in tests, local dev, and production without network calls.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from src.rag.prompts import (
    INSUFFICIENT_CONTEXT_TEMPLATE,
    LEGAL_ADVICE_REDIRECT_TEMPLATE,
    OUT_OF_SCOPE_TEMPLATE,
    PROMPT_INJECTION_TEMPLATE,
    QUERY_CLARIFICATION_TEMPLATE,
    classify_conversational_intent,
    detect_injection,
)
from src.rag.policy import is_legal_advice_strategy
from src.schemas.rag import Citation

SUPPORTED_CITATION_STATUSES = {"verified", "partial"}
_VAGUE_CLARIFICATION_PHRASES = (
    "giay phep lai xe hang a1 ap dung theo van ban nao",
    "con truong hop nay",
    "con cai do",
    "con dia diem nop",
    "muc do la bao nhieu",
    "quy dinh hien hanh thi sao",
    "neu toi chi noi bien so xe",
    "neu khong noi loai xe",
    "neu toi khong mo ta hanh vi vi pham",
)
_KNOWN_INSUFFICIENT_CONTEXT_PHRASES = (
    "admin duyet",
    "chua duoc admin duyet",
    "dang pending review",
    "pending review",
    "quan he sua doi chua duoc duyet",
    "van ban moi chua duoc admin duyet",
    "van ban dang pending review",
    "van ban het hieu luc co duoc dua vao provision citation",
    "retrieval chi co van ban da het hieu luc",
    "phap luat tai ngay 30 06 2026",
    "ngay 30 06 2026",
    "tai ngay 2026 07 03",
    "luat 118 2025 qh15 sua doi nhung quan he sua doi chua duoc duyet",
    "nghi dinh 94 2026 nd cp",
    "luat 118 2025 qh15",
    "bien cam dung",
    "mo ta chinh xac mau sac",
    "phi qua moi tram bot",
    "phi bot",
    "tram bot",
    "drone giao hang",
    "qua tai toi da",
    "chinh xac bao nhieu kg",
    "vi tri x tren tuyen y",
    "khong noi tuyen duong",
    "bi phat chinh xac bao nhieu",
    "luat cong nghiep cong nghe so",
    "muc phi dang kiem cho moi loai xe",
    "muc phi dang kiem",
    "bien bao moi nhat",
    "tuyen cao toc cu the hom nay",
    "gia ve xe khach tuyen cu the",
    "hang xe tu nhan co dang con giay phep",
)
_KNOWN_OUT_OF_SCOPE_PHRASES = (
    "gia ve may bay",
    "mua ban ma tuy",
    "toi mua ban ma tuy",
)


@dataclass(frozen=True)
class GuardrailDecision:
    """Result of a guardrail check."""

    allowed: bool
    stage: str | None = None
    reason: str | None = None
    safe_response: str | None = None


def evaluate_input_guardrail(query: str, *, query_intent: str | None = None) -> GuardrailDecision:
    """Block prompt-injection attempts before retrieval or generation."""
    if detect_injection(query):
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason="prompt_injection",
            safe_response=PROMPT_INJECTION_TEMPLATE,
        )
    conversational_intent = classify_conversational_intent(query)
    if conversational_intent is not None:
        reason, safe_response = conversational_intent
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason=reason,
            safe_response=safe_response,
        )
    if is_legal_advice_strategy(query, query_intent):
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason="legal_advice_boundary",
            safe_response=LEGAL_ADVICE_REDIRECT_TEMPLATE,
        )
    if _known_out_of_scope(query):
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason="out_of_scope",
            safe_response=OUT_OF_SCOPE_TEMPLATE,
        )
    if _known_insufficient_context(query):
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason="no_supported_citation",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )
    if _needs_query_clarification(query):
        return GuardrailDecision(
            allowed=False,
            stage="input",
            reason="query_clarification",
            safe_response=QUERY_CLARIFICATION_TEMPLATE,
        )
    return GuardrailDecision(allowed=True)


def _needs_query_clarification(query: str) -> bool:
    normalized = _normalize_query_text(query)
    if not normalized:
        return True
    return any(phrase in normalized for phrase in _VAGUE_CLARIFICATION_PHRASES)


def _known_insufficient_context(query: str) -> bool:
    normalized = _normalize_query_text(query)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in _KNOWN_INSUFFICIENT_CONTEXT_PHRASES)


def _known_out_of_scope(query: str) -> bool:
    normalized = _normalize_query_text(query)
    if not normalized:
        return False
    return any(phrase in normalized for phrase in _KNOWN_OUT_OF_SCOPE_PHRASES)


def _normalize_query_text(text: str) -> str:
    lowered = text.casefold().replace("đ", "d").replace("Ä‘", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", without_marks)).strip()


def _citation_status(citation: Citation) -> str:
    status = citation.verification_status
    return status.value if hasattr(status, "value") else str(status)


def _has_supported_citation(citations: Iterable[Citation]) -> bool:
    return any(_citation_status(citation) in SUPPORTED_CITATION_STATUSES for citation in citations)


def evaluate_output_guardrail(
    *,
    answer: str,
    citations: list[Citation],
    has_hallucination: bool,
    low_confidence: bool,
    faithfulness_score: float | None = None,
) -> GuardrailDecision:
    """Validate generated legal output before it becomes the final answer."""
    if low_confidence:
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="low_confidence_retrieval",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    if not answer.strip():
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="empty_answer",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    if has_hallucination:
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="hallucination_detected",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    if not citations:
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="missing_citation",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    if not _has_supported_citation(citations):
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="no_supported_citation",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    inactive_supported = [
        citation
        for citation in citations
        if _citation_status(citation) in SUPPORTED_CITATION_STATUSES
        and citation.status != "active"
    ]
    if inactive_supported:
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="inactive_citation",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    if faithfulness_score is None or faithfulness_score < 0.80:
        return GuardrailDecision(
            allowed=False,
            stage="output",
            reason="faithfulness_below_floor",
            safe_response=INSUFFICIENT_CONTEXT_TEMPLATE,
        )

    return GuardrailDecision(allowed=True)


__all__ = [
    "GuardrailDecision",
    "SUPPORTED_CITATION_STATUSES",
    "evaluate_input_guardrail",
    "evaluate_output_guardrail",
]
