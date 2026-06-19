"""Deterministic follow-up resolution using recent conversation context."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.rag.guardrails import evaluate_input_guardrail
from src.rag.intent import classify_query_intent
from src.rag.query_policy import get_query_policy
from src.rag.retrieval.query_utils import semantic_document_scope_numbers


@dataclass(frozen=True)
class FollowUpResolution:
    retrieval_query: str
    used_history: bool
    confidence: float
    reason: str
    needs_clarification: bool = False


def _normalize(text: str) -> str:
    lowered = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    compact = re.sub(r"[^a-z0-9\s/]", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def _extract_recent_user_turns(conversation_context: str) -> list[str]:
    turns: list[str] = []
    for line in conversation_context.splitlines():
        stripped = line.strip()
        if stripped.startswith("Người dùng: "):
            turns.append(stripped.removeprefix("Người dùng: ").strip())
        elif stripped.startswith("Nguoi dung: "):
            turns.append(stripped.removeprefix("Nguoi dung: ").strip())
        elif stripped.startswith("NgÆ°á»i dÃ¹ng: "):
            turns.append(stripped.removeprefix("NgÆ°á»i dÃ¹ng: ").strip())
        elif stripped.startswith("NgÃ†Â°Ã¡Â»Âi dÃƒÂ¹ng: "):
            turns.append(stripped.removeprefix("NgÃ†Â°Ã¡Â»Âi dÃƒÂ¹ng: ").strip())
    return [turn for turn in turns if turn]


def _contains_any(normalized_text: str, phrases: tuple[str, ...]) -> bool:
    padded = f" {normalized_text} "
    return any(f" {phrase} " in padded for phrase in phrases)


def _looks_like_follow_up(query: str, query_intent: str | None) -> bool:
    policy = get_query_policy().follow_up
    normalized = _normalize(query)
    if not normalized:
        return False
    if semantic_document_scope_numbers(query):
        return False
    if _looks_like_standalone_topic(query) and not any(
        normalized.startswith(prefix) for prefix in policy.prefixes
    ):
        return False
    if any(normalized.startswith(prefix) for prefix in policy.prefixes):
        return True
    if _contains_any(normalized, policy.phrases):
        return True
    if query_intent == "ambiguous":
        return True
    if len(normalized.split()) <= 4 and query_intent in {"penalty", "procedure", "obligation"}:
        return True
    return False


def _looks_like_standalone_topic(query: str) -> bool:
    policy = get_query_policy().follow_up
    normalized = _normalize(query)
    if not normalized:
        return False
    if re.search(r"\b\d{1,3}/\d{4}/[^\s,.;:!?)]*", query, re.IGNORECASE):
        return True
    return _contains_any(normalized, policy.standalone_topic_hints)


def _history_topic_confidence(query: str, history_turn: str) -> tuple[float, str]:
    policy = get_query_policy().follow_up
    history_guard = evaluate_input_guardrail(history_turn)
    if not history_guard.allowed and history_guard.reason in policy.history_question_blockers:
        return 0.0, "history_blocked_by_guardrail"

    history_intent = classify_query_intent(history_turn).query_intent
    if history_intent in policy.low_signal_user_intents:
        return 0.25, "history_topic_ambiguous"

    normalized_history = _normalize(history_turn)
    if len(normalized_history.split()) < 4:
        return 0.35, "history_topic_too_short"

    if _contains_any(normalized_history, policy.topic_hints):
        return 0.92, "history_topic_clear"

    if history_intent in {
        "definition",
        "obligation",
        "penalty",
        "procedure",
        "document_lookup",
        "effective_status",
        "comparison_history",
    }:
        return 0.82, "history_intent_clear"

    return 0.55, "history_topic_weak"


def resolve_follow_up(
    *,
    query: str,
    query_intent: str | None,
    conversation_context: str | None,
) -> FollowUpResolution:
    normalized_query = re.sub(r"\s+", " ", query).strip()
    if not normalized_query:
        return FollowUpResolution(
            retrieval_query="",
            used_history=False,
            confidence=0.0,
            reason="empty_query",
        )

    if _looks_like_standalone_topic(normalized_query) and not _looks_like_follow_up(
        normalized_query, query_intent
    ):
        return FollowUpResolution(
            retrieval_query=normalized_query,
            used_history=False,
            confidence=1.0,
            reason="standalone_query",
        )

    if not _looks_like_follow_up(normalized_query, query_intent):
        return FollowUpResolution(
            retrieval_query=normalized_query,
            used_history=False,
            confidence=1.0 if _looks_like_standalone_topic(normalized_query) else 0.0,
            reason="standalone_query",
        )

    user_turns = _extract_recent_user_turns(conversation_context or "")
    if not user_turns:
        return FollowUpResolution(
            retrieval_query=normalized_query,
            used_history=False,
            confidence=0.0,
            reason="missing_history_for_follow_up",
            needs_clarification=True,
        )

    last_user_turn = user_turns[-1]
    confidence, reason = _history_topic_confidence(normalized_query, last_user_turn)
    if confidence >= 0.75:
        return FollowUpResolution(
            retrieval_query=f"{last_user_turn} {normalized_query}"[:1400],
            used_history=True,
            confidence=confidence,
            reason=reason,
        )

    if _looks_like_standalone_topic(normalized_query):
        return FollowUpResolution(
            retrieval_query=normalized_query,
            used_history=False,
            confidence=0.4,
            reason="standalone_topic_overrides_history",
        )

    return FollowUpResolution(
        retrieval_query=normalized_query,
        used_history=False,
        confidence=confidence,
        reason=reason,
        needs_clarification=True,
    )


__all__ = ["FollowUpResolution", "resolve_follow_up"]
