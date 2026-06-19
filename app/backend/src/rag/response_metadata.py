"""Deterministic chat response metadata for backward-compatible API upgrades."""

from __future__ import annotations

from typing import Any

from src.rag.policy import (
    classify_answer_mode,
    classify_risk_level,
    strip_disclaimer,
)

_SUPPORTED_CITATION_STATUSES = {"verified", "partial"}


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _provision_citation(item: Any) -> dict[str, Any] | None:
    status = _value(item, "status")
    verification_status = _enum_value(_value(item, "verification_status"))
    chunk_id = _value(item, "chunk_id")
    doc_id = _value(item, "doc_id")
    if (
        status != "active"
        or verification_status not in _SUPPORTED_CITATION_STATUSES
        or not chunk_id
        or not doc_id
    ):
        return None
    return {
        "document_id": doc_id,
        "article_num": _value(item, "article_num"),
        "clause_num": _value(item, "clause_num"),
        "point_num": _value(item, "point_num"),
        "effective_status": status,
        "retrieval_unit_id": chunk_id,
    }


def _provision_citations(citations: list[Any]) -> list[dict[str, Any]]:
    provision_citations: list[dict[str, Any]] = []
    for item in citations:
        mapped = _provision_citation(item)
        if mapped is not None:
            provision_citations.append(mapped)
    return provision_citations


def _document_source(item: Any) -> dict[str, Any] | None:
    document_id = _value(item, "document_id")
    if not document_id:
        return None
    return {
        "document_id": document_id,
        "title": _value(item, "title"),
        "issuing_body": _value(item, "issuing_body"),
        "date": _value(item, "date"),
        "url": _value(item, "url"),
    }


def _document_sources(items: list[Any] | None) -> list[dict[str, Any]]:
    mapped_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items or []:
        mapped = _document_source(item)
        if mapped is None:
            continue
        document_id = str(mapped["document_id"])
        if document_id in seen_ids:
            continue
        seen_ids.add(document_id)
        mapped_items.append(mapped)
    return mapped_items


def _document_sources_from_citations(citations: list[Any]) -> list[dict[str, Any]]:
    mapped_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in citations:
        doc_id = _value(item, "doc_id")
        if not doc_id or str(doc_id) in seen_ids:
            continue
        seen_ids.add(str(doc_id))
        mapped_items.append(
            {
                "document_id": doc_id,
                "title": _value(item, "doc_title"),
                "issuing_body": None,
                "date": _value(item, "effective_date"),
                "url": _value(item, "source_url"),
            }
        )
    return mapped_items


def _merge_document_sources(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in [*primary, *secondary]:
        document_id = item.get("document_id")
        if not document_id or str(document_id) in seen_ids:
            continue
        seen_ids.add(str(document_id))
        merged.append(item)
    return merged


def _historical_reference(item: Any) -> dict[str, Any] | None:
    status = _value(item, "status")
    doc_id = _value(item, "doc_id") or _value(item, "document_id")
    if not doc_id or status == "active":
        return None
    return {
        "document_id": doc_id,
        "title": _value(item, "doc_title") or _value(item, "title"),
        "article_num": _value(item, "article_num"),
        "clause_num": _value(item, "clause_num"),
        "point_num": _value(item, "point_num"),
        "effective_from": _value(item, "effective_date") or _value(item, "effective_from"),
        "effective_to": _value(item, "expiry_date") or _value(item, "effective_to"),
        "status": status,
        "replaced_by": _value(item, "replaced_by"),
    }


def _historical_references(
    citations: list[Any],
    explicit_items: list[Any] | None = None,
) -> list[dict[str, Any]]:
    mapped_items: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for item in [*(explicit_items or []), *citations]:
        mapped = _historical_reference(item)
        if mapped is None:
            continue
        key = (
            mapped["document_id"],
            mapped.get("article_num"),
            mapped.get("clause_num"),
            mapped.get("point_num"),
            mapped.get("status"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        mapped_items.append(mapped)
    return mapped_items


def _confidence(
    *,
    answer_mode: str,
    faithfulness_score: float | None,
    guardrail_reason: str | None,
    has_provision_citations: bool,
) -> dict[str, str]:
    if answer_mode in {"clarification_needed", "insufficient_evidence"}:
        return {"level": "low", "reason": guardrail_reason or "insufficient_evidence"}
    if answer_mode == "out_of_scope":
        return {"level": "high", "reason": guardrail_reason or "out_of_scope"}
    if answer_mode == "multiple_possibilities":
        return {"level": "medium", "reason": "strategy_or_fact_dependent_request"}
    if answer_mode == "historical":
        return {"level": "medium", "reason": "historical_or_comparison_request"}
    if has_provision_citations and faithfulness_score is not None:
        if faithfulness_score >= 0.95:
            return {"level": "high", "reason": "verified_citations_high_faithfulness"}
        return {"level": "medium", "reason": "verified_citations"}
    if answer_mode == "summary":
        return {"level": "medium", "reason": "deterministic_summary_path"}
    return {"level": "medium", "reason": guardrail_reason or "metadata_default"}


def build_chat_response_metadata(
    *,
    content: str,
    citations: list[Any],
    faithfulness_score: float | None,
    is_out_of_scope: bool,
    query_intent: str | None = None,
    guardrail_reason: str | None = None,
    query_text: str | None = None,
    low_confidence: bool = False,
    document_sources: list[Any] | None = None,
    historical_references: list[Any] | None = None,
) -> dict[str, Any]:
    provision_citations = _provision_citations(citations)
    mapped_document_sources = _document_sources(document_sources)
    mapped_document_sources = _merge_document_sources(
        mapped_document_sources,
        _document_sources_from_citations(citations),
    )
    mapped_historical_references = _historical_references(citations, historical_references)
    answer_mode = classify_answer_mode(
        content=content,
        is_out_of_scope=is_out_of_scope,
        query_intent=query_intent,
        guardrail_reason=guardrail_reason,
        query_text=query_text,
        low_confidence=low_confidence,
    )
    stripped = strip_disclaimer(content)
    return {
        "risk_level": classify_risk_level(
            answer_mode=answer_mode,
            query_intent=query_intent,
            query_text=query_text,
            has_provision_citations=bool(provision_citations),
        ),
        "answer_mode": answer_mode,
        "confidence": _confidence(
            answer_mode=answer_mode,
            faithfulness_score=faithfulness_score,
            guardrail_reason=guardrail_reason,
            has_provision_citations=bool(provision_citations),
        ),
        "provision_citations": provision_citations,
        "document_sources": mapped_document_sources,
        "historical_references": mapped_historical_references,
        "clarification_question": (
            stripped if answer_mode == "clarification_needed" and stripped else None
        ),
    }


__all__ = ["build_chat_response_metadata"]
