"""Persist redacted chat quality evidence and actionable issues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.observability import redact_pii
from src.models.quality import QualityIssue, QualityObservation
from src.rag.prompts import RAG_PROMPT_VERSION
from src.rag.query_policy import get_query_policy
from src.rag.response_metadata import build_chat_response_metadata


@dataclass(frozen=True, slots=True)
class IssueSpec:
    issue_type: str
    severity: str
    title: str
    summary: str
    machine_reason: str | None = None


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _serialize_citations(citations: list[Any]) -> list[dict]:
    serialized: list[dict] = []
    for citation in citations:
        if hasattr(citation, "model_dump"):
            serialized.append(citation.model_dump(mode="json"))
        elif isinstance(citation, dict):
            serialized.append(citation)
    return serialized


def _serialize_evidence(chunks: list[Any]) -> list[dict]:
    evidence: list[dict] = []
    for chunk in chunks[:8]:
        evidence.append(
            {
                "chunk_id": _value(chunk, "chunk_id"),
                "doc_id": _value(chunk, "doc_id"),
                "doc_title": _value(chunk, "doc_title"),
                "status": _value(chunk, "status"),
                "article_num": _value(chunk, "article_num"),
                "clause_num": _value(chunk, "clause_num"),
                "point_num": _value(chunk, "point_num"),
                "locator_label": _value(chunk, "locator_label"),
                "rerank_score": _value(chunk, "rerank_score"),
                "text_snippet": redact_pii(str(_value(chunk, "text_snippet", "")))[:500],
            }
        )
    return evidence


def _pipeline_metadata(values: dict[str, Any], citations: list[dict], chunks: list[Any]) -> dict:
    scope = values.get("scope_result")
    response_policy = build_chat_response_metadata(
        content=values.get("final_response") or "",
        citations=list(values.get("verified_citations") or []),
        faithfulness_score=values.get("faithfulness_score"),
        is_out_of_scope=bool(values.get("is_out_of_scope", False)),
        query_intent=values.get("query_intent"),
        guardrail_reason=values.get("guardrail_reason"),
        query_text=values.get("query"),
        low_confidence=bool(values.get("low_confidence", False)),
        document_sources=values.get("response_document_sources"),
        historical_references=values.get("response_historical_references"),
    )
    return {
        "versions": {
            "generation_model": settings.MODEL_NAME,
            "prompt": RAG_PROMPT_VERSION,
            "query_policy": get_query_policy().version,
            "embedding_model": settings.EMBEDDING_MODEL_NAME,
            "ranking_model": settings.LOCAL_RANK_VERSION,
        },
        "scope": {
            "label": _enum_value(_value(scope, "label")) if scope is not None else None,
            "score": _value(scope, "score"),
        },
        "retrieval": {
            "status_filter": values.get("status_filter"),
            "candidate_count": values.get("retrieval_candidate_count"),
            "context_count": len(chunks),
            "follow_up_used": bool(values.get("follow_up_used", False)),
            "follow_up_confidence": values.get("follow_up_confidence"),
            "follow_up_reason": values.get("follow_up_reason"),
        },
        "ranking": {
            "used": bool(values.get("reranker_used", False)),
            "failed": bool(values.get("reranker_failed", False)),
            "error_code": values.get("reranker_error_code"),
            "top_score": values.get("rerank_top_score"),
        },
        "verification": {
            "citation_count": len(citations),
            "faithfulness_score": values.get("faithfulness_score"),
            "has_hallucination": bool(values.get("has_hallucination", False)),
        },
        "response_policy": {
            "risk_level": response_policy["risk_level"],
            "answer_mode": response_policy["answer_mode"],
            "confidence": response_policy["confidence"],
        },
    }


def issue_specs_from_result(
    *,
    active_filter_violation: bool,
    disclaimer_missing: bool,
    has_hallucination: bool,
    low_confidence: bool,
    citations: list[Any],
) -> list[IssueSpec]:
    specs: list[IssueSpec] = []
    if active_filter_violation:
        specs.append(
            IssueSpec(
                issue_type="active_filter_violation",
                severity="critical",
                title="Nguồn không còn active xuất hiện trong câu trả lời",
                summary="Cần khóa release và kiểm tra filter trước retrieval.",
                machine_reason="inactive_citation",
            )
        )
    if disclaimer_missing:
        specs.append(
            IssueSpec(
                issue_type="disclaimer_missing",
                severity="critical",
                title="Câu trả lời pháp lý thiếu disclaimer",
                summary="Output pháp lý không đáp ứng yêu cầu disclaimer bắt buộc.",
                machine_reason="disclaimer_missing",
            )
        )
    if has_hallucination:
        specs.append(
            IssueSpec(
                issue_type="unsupported_claim",
                severity="critical",
                title="Claim pháp lý không có căn cứ đủ chắc",
                summary="Verifier phát hiện citation bị chặn hoặc phần lớn citation không xác minh được.",
                machine_reason="hallucination_detected",
            )
        )
    weak_citations = [
        citation
        for citation in citations
        if _enum_value(_value(citation, "verification_status"))
        in {"partial", "unverified", "blocked"}
    ]
    if weak_citations and not has_hallucination:
        specs.append(
            IssueSpec(
                issue_type="citation_verification",
                severity="high",
                title="Citation cần reviewer kiểm tra",
                summary=f"{len(weak_citations)} citation chưa được xác minh đầy đủ.",
                machine_reason="weak_citation",
            )
        )
    if low_confidence:
        specs.append(
            IssueSpec(
                issue_type="low_confidence",
                severity="medium",
                title="Retrieval chưa tìm được căn cứ đủ mạnh",
                summary="Chatbot đã abstain an toàn; cần xác định KB gap hay retrieval miss.",
                machine_reason="low_confidence_retrieval",
            )
        )
    return specs


async def start_observation(
    db_session: AsyncSession,
    *,
    trace_id: str,
    session_id: str,
    user_id: str | None,
    query: str,
    external_tracing_enabled: bool,
) -> QualityObservation:
    observation = QualityObservation(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        environment=settings.APP_ENV.lower(),
        query_text=redact_pii(query),
        external_tracing_enabled=external_tracing_enabled,
    )
    db_session.add(observation)
    await db_session.commit()
    return observation


async def complete_observation(
    db_session: AsyncSession,
    observation: QualityObservation,
    *,
    values: dict[str, Any],
    latency_ms: int,
    first_token_latency_ms: int | None = None,
) -> list[QualityIssue]:
    citations_raw = list(values.get("verified_citations") or [])
    citations = _serialize_citations(citations_raw)
    chunks = list(values.get("retrieved_contexts") or [])
    is_legal_output = bool(chunks or citations) and not values.get("is_out_of_scope", False)
    active_filter_violation = any(
        _value(citation, "status") != "active" for citation in citations_raw
    )
    disclaimer_missing = is_legal_output and not values.get("disclaimer_appended", False)
    has_hallucination = bool(values.get("has_hallucination", False))
    low_confidence = bool(values.get("low_confidence", False))

    observation.status = "succeeded"
    observation.response_text = redact_pii(values.get("final_response") or "")
    observation.citations = citations
    observation.evidence = _serialize_evidence(chunks)
    observation.pipeline_metadata = _pipeline_metadata(values, citations, chunks)
    observation.faithfulness_score = values.get("faithfulness_score")
    observation.is_out_of_scope = bool(values.get("is_out_of_scope", False))
    observation.low_confidence = low_confidence
    observation.has_hallucination = has_hallucination
    observation.active_filter_violation = active_filter_violation
    observation.disclaimer_missing = disclaimer_missing
    observation.guardrail_stage = values.get("guardrail_stage")
    observation.guardrail_reason = values.get("guardrail_reason")
    observation.first_token_latency_ms = first_token_latency_ms
    observation.latency_ms = latency_ms
    observation.completed_at = datetime.now(UTC)

    specs = issue_specs_from_result(
        active_filter_violation=active_filter_violation,
        disclaimer_missing=disclaimer_missing,
        has_hallucination=has_hallucination,
        low_confidence=low_confidence,
        citations=citations_raw,
    )
    issues = [
        QualityIssue(
            trace_id=observation.trace_id,
            issue_type=spec.issue_type,
            severity=spec.severity,
            title=spec.title,
            summary=spec.summary,
            machine_reason=spec.machine_reason,
            evidence={
                "guardrail_reason": observation.guardrail_reason,
                "citation_count": len(citations),
                "retrieved_context_count": len(chunks),
                "pipeline": observation.pipeline_metadata,
            },
        )
        for spec in specs
    ]
    db_session.add_all(issues)
    await db_session.commit()
    return issues


async def fail_observation(
    db_session: AsyncSession,
    observation: QualityObservation,
    *,
    error: str,
    latency_ms: int,
    cancelled: bool = False,
) -> QualityIssue | None:
    observation.status = "cancelled" if cancelled else "failed"
    observation.error_summary = redact_pii(error)[:2000]
    observation.latency_ms = latency_ms
    observation.completed_at = datetime.now(UTC)
    issue = None
    if not cancelled:
        issue = QualityIssue(
            trace_id=observation.trace_id,
            issue_type="chat_error",
            severity="high",
            title="Chat request không hoàn tất",
            summary="Pipeline gặp lỗi trước khi trả response hoàn chỉnh.",
            machine_reason="chat_pipeline_error",
            evidence={"error": observation.error_summary},
        )
        db_session.add(issue)
    await db_session.commit()
    return issue


__all__ = [
    "IssueSpec",
    "complete_observation",
    "fail_observation",
    "issue_specs_from_result",
    "start_observation",
]
