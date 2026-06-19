"""Deterministic query-intent classification for legal chat."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.rag.query_policy import get_query_policy


@dataclass(frozen=True)
class IntentResult:
    query_intent: str
    document_number: str | None = None


_DOC_NUMBER_PATTERN = re.compile(r"\b(\d{1,3}/\d{4}/[^\s,.;:!?)]*)", re.IGNORECASE)
def _normalize(text: str) -> str:
    lowered = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    compact = re.sub(r"[^a-z0-9\s/]", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def _extract_document_number(query: str) -> str | None:
    match = _DOC_NUMBER_PATTERN.search(query)
    if not match:
        return None
    return match.group(1).strip().rstrip(".,;:!?")


def _contains_any(normalized: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {normalized} "
    return any(f" {phrase} " in padded for phrase in phrases)


def classify_query_intent(query: str) -> IntentResult:
    policy = get_query_policy().intent_hints
    normalized = _normalize(query)
    document_number = _extract_document_number(query)

    if document_number and _contains_any(normalized, policy.summary_phrases):
        return IntentResult("document_summary_standard", document_number)
    if _contains_any(normalized, policy.comparison_history_phrases):
        return IntentResult("comparison_history", document_number)
    if document_number and _contains_any(normalized, policy.effective_status_phrases):
        return IntentResult("effective_status", document_number)
    if document_number and _contains_any(normalized, policy.document_lookup_phrases):
        return IntentResult("document_lookup", document_number)
    if _contains_any(normalized, policy.definition_phrases):
        return IntentResult("definition", document_number)
    if _contains_any(normalized, policy.penalty_phrases):
        return IntentResult("penalty", document_number)
    if _contains_any(normalized, policy.procedure_phrases):
        return IntentResult("procedure", document_number)
    if _contains_any(normalized, policy.obligation_phrases):
        return IntentResult("obligation", document_number)
    if not document_number and (
        _contains_any(normalized, policy.ambiguous_phrases)
        or (
            len(normalized.split()) <= 3
            and _contains_any(normalized, policy.ambiguous_short_cues)
        )
    ):
        return IntentResult("ambiguous", None)
    return IntentResult("general_legal", document_number)


__all__ = ["IntentResult", "classify_query_intent"]
