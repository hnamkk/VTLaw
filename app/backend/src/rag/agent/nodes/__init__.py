"""Graph nodes for the RAG agent pipeline (spec 09, 13; plan sect6).

Each node receives state and optionally a LangGraph RunnableConfig.
The db_session and llm dependencies are passed via config["configurable"]
so the graph stays pure (no global state) and is testable with mocks.

Usage from API layer:
    config = {
        "configurable": {
            "thread_id": session_id,
            "db_session": async_session,
            "llm": chat_model,
        }
    }
    await graph.ainvoke(initial_state, config)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import select

from src.legal_kb.evidence import assemble_evidence_bundle
from src.legal_kb.temporal import resolve_query_date
from src.models.legal_kb import (
    LegalKbRelation,
    LegalKbRevision,
    LegalKbDocument,
    LegalKbRetrievalUnit,
    LegalKbSummary,
)
from src.rag.agent.state import AgentState
from src.rag.embedding import embed_query
from src.rag.evidence_policy import evaluate_evidence_policy
from src.rag.follow_up import resolve_follow_up
from src.rag.guardrails import evaluate_input_guardrail, evaluate_output_guardrail
from src.rag.intent import classify_query_intent
from src.rag.prompts import (
    INSUFFICIENT_CONTEXT_TEMPLATE,
    LEGAL_DISCLAIMER,
    OUT_OF_SCOPE_TEMPLATE,
    QUERY_CLARIFICATION_TEMPLATE,
    SMALL_TALK_TEMPLATE,
    SYSTEM_PROMPT,
    format_rag_prompt,
)
from src.rag.reranking import rerank_chunks
from src.rag.retrieval.context_packer import format_context, pack_context
from src.rag.retrieval.hybrid_legal import (
    _document_ids_for_explicit_refs,
    _extract_document_refs,
    future_effective_notice_for_query,
    hybrid_retrieve_legal,
)
from src.rag.retrieval.query_utils import (
    expand_query_for_retrieval,
    query_for_local_ranking,
    semantic_document_scope_numbers,
)
from src.rag.retrieval.scope import classify_scope, is_small_talk_query
from src.rag.verification import (
    citations_from_retrieval_units,
    compute_faithfulness_score,
    has_hallucination,
    verify_citations,
)
from src.schemas.rag import ScopeLabel, ScopeResult, VerificationStatus

logger = logging.getLogger(__name__)

_DOC_NUMBER_QUERY_PATTERN = re.compile(r"\b\d{1,3}/\d{4}/[^\s,.;:!?)]+", re.IGNORECASE)
_SUMMARY_GUARDRAIL_REASON = "legal_kb_standard_summary"
_DOC_NOT_FOUND_GUARDRAIL_REASON = "legal_kb_document_not_found"
_DOC_LOOKUP_GUARDRAIL_REASON = "legal_kb_document_lookup"
_EFFECTIVE_STATUS_GUARDRAIL_REASON = "legal_kb_effective_status"
_HISTORICAL_LOOKUP_GUARDRAIL_REASON = "legal_kb_historical_lookup"
_EVIDENCE_CLARIFICATION_GUARDRAIL_REASON = "evidence_clarification"
_EVIDENCE_MULTIPLE_GUARDRAIL_REASON = "evidence_multiple_possibilities"
_EVIDENCE_INSUFFICIENT_GUARDRAIL_REASON = "evidence_insufficient"
_DIRECT_EVIDENCE_GUARDRAIL_REASONS = {
    _EVIDENCE_CLARIFICATION_GUARDRAIL_REASON,
    _EVIDENCE_MULTIPLE_GUARDRAIL_REASON,
    _EVIDENCE_INSUFFICIENT_GUARDRAIL_REASON,
}
_DIRECT_INPUT_RESPONSE_REASONS = {
    "prompt_injection",
    "temporal_clarification",
    "query_clarification",
    "assistant_identity",
    "assistant_capability",
    "assistant_role",
    "assistant_legal_value",
    "assistant_liability",
    "assistant_source_policy",
    "assistant_how_to_use",
    "legal_advice_boundary",
    "no_supported_citation",
    "out_of_scope",
}


@dataclass(frozen=True)
class _LegalKbDocumentBundle:
    document: LegalKbDocument
    source_url: str | None = None


def _normalize_lookup_text(value: str) -> str:
    normalized = value.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _summary_document_number(query: str) -> str | None:
    normalized = _normalize_lookup_text(query)
    if "tom tat" not in normalized and "summary" not in normalized:
        return None
    match = _DOC_NUMBER_QUERY_PATTERN.search(query)
    if not match:
        return None
    return match.group(0).strip().rstrip(".,;:!?")


async def _legal_kb_standard_summary_response(db_session, query: str) -> str | None:
    document_number = _summary_document_number(query)
    if not document_number:
        return None
    stmt = (
        select(LegalKbSummary.content)
        .join(
            LegalKbRevision,
            LegalKbRevision.revision_id == LegalKbSummary.revision_id,
        )
        .join(
            LegalKbDocument,
            LegalKbDocument.document_id == LegalKbSummary.document_id,
        )
        .where(
            LegalKbDocument.document_number.ilike(document_number),
            LegalKbDocument.legal_status == "active",
            LegalKbSummary.review_status == "approved",
            LegalKbRevision.publication_status == "published",
            LegalKbRevision.review_status == "approved",
        )
        .order_by(LegalKbRevision.created_at.desc())
        .limit(1)
    )
    return await db_session.scalar(stmt)


async def _legal_kb_standard_summary_bundle(db_session, query: str) -> tuple[str | None, dict | None]:
    document_number = _summary_document_number(query)
    if not document_number:
        return None, None
    content = await _legal_kb_standard_summary_response(db_session, query)
    bundle = await _get_legal_kb_published_document_bundle_by_number(db_session, document_number)
    return content, (_document_source_from_bundle(bundle) if bundle is not None else None)


def _explicit_document_number(query: str) -> str | None:
    refs = _extract_document_refs(query)
    return refs[0] if refs else None


def _legal_kb_document_not_found_response(document_number: str) -> str:
    return (
        f"Xin lỗi, tôi chưa tìm thấy văn bản số hiệu {document_number} "
        "đang được công bố trong kho dữ liệu hiện tại."
    )


def _legal_kb_summary_missing_response(document_number: str) -> str:
    return (
        f"Xin lỗi, tôi chưa có bản tóm tắt chuẩn đã duyệt "
        f"cho văn bản số hiệu {document_number}."
    )


def _format_vi_date(value: date | None) -> str:
    if value is None:
        return "chưa rõ"
    return value.strftime("%d/%m/%Y")


def _legal_status_label(status: str | None) -> str:
    labels = {
        "active": "đang có hiệu lực",
        "future_effective": "chưa có hiệu lực",
        "expired": "đã hết hiệu lực",
        "suspended": "đang tạm ngừng công bố",
        "unknown": "chưa xác định rõ tình trạng hiệu lực",
    }
    return labels.get(str(status or "").lower(), "chưa xác định rõ tình trạng hiệu lực")


def _document_type_label(document_type: str | None) -> str:
    labels = {
        "luat": "luật",
        "bo_luat": "bộ luật",
        "nghi_dinh": "nghị định",
        "thong_tu": "thông tư",
        "thong_tu_lien_tich": "thông tư liên tịch",
        "quyet_dinh": "quyết định",
        "nghi_quyet": "nghị quyết",
        "van_ban_hop_nhat": "văn bản hợp nhất",
        "quy_chuan": "quy chuẩn",
        "tieu_chuan": "tiêu chuẩn",
    }
    key = str(document_type or "").strip().lower()
    return labels.get(key, (document_type or "văn bản").replace("_", " ").lower())


async def _get_legal_kb_published_document_by_number(db_session, document_number: str):
    bundle = await _get_legal_kb_published_document_bundle_by_number(db_session, document_number)
    return bundle.document if bundle is not None else None


async def _get_legal_kb_document_bundle_by_number(
    db_session,
    document_number: str,
    *,
    publication_statuses: tuple[str, ...],
    active_only: bool,
) -> _LegalKbDocumentBundle | None:
    if not hasattr(db_session, "execute"):
        return None
    stmt = (
        select(
            LegalKbDocument,
            LegalKbRevision.source_url.label("revision_source_url"),
        )
        .join(
            LegalKbRevision,
            LegalKbRevision.document_id == LegalKbDocument.document_id,
        )
        .where(
            LegalKbDocument.document_number.ilike(document_number),
            LegalKbRevision.publication_status.in_(publication_statuses),
            LegalKbRevision.review_status == "approved",
        )
        .order_by(LegalKbRevision.created_at.desc())
        .limit(1)
    )
    if active_only:
        stmt = stmt.where(LegalKbDocument.legal_status == "active")
    row = await db_session.execute(stmt)
    result = row.first()
    if result is None:
        return None
    return _LegalKbDocumentBundle(
        document=result[0],
        source_url=result[1],
    )


async def _get_legal_kb_published_document_bundle_by_number(
    db_session,
    document_number: str,
) -> _LegalKbDocumentBundle | None:
    return await _get_legal_kb_document_bundle_by_number(
        db_session,
        document_number,
        publication_statuses=("published",),
        active_only=True,
    )


async def _get_legal_kb_lifecycle_document_bundle_by_number(
    db_session,
    document_number: str,
) -> _LegalKbDocumentBundle | None:
    return await _get_legal_kb_document_bundle_by_number(
        db_session,
        document_number,
        publication_statuses=("published", "suspended", "archived"),
        active_only=False,
    )


def _document_source_from_bundle(bundle: _LegalKbDocumentBundle | None) -> dict | None:
    if bundle is None:
        return None
    document = bundle.document
    return {
        "document_id": document.document_id,
        "title": document.title,
        "issuing_body": document.issuing_authority,
        "date": document.issued_date or document.effective_date,
        "url": bundle.source_url,
    }


async def _find_replacement_bundle_for_document(
    db_session,
    document_id: str,
) -> _LegalKbDocumentBundle | None:
    if not hasattr(db_session, "execute"):
        return None
    stmt = (
        select(
            LegalKbRelation,
            LegalKbDocument,
            LegalKbRevision.source_url.label("revision_source_url"),
        )
        .join(
            LegalKbDocument,
            LegalKbDocument.document_id == LegalKbRelation.source_document_id,
        )
        .join(
            LegalKbRevision,
            LegalKbRevision.document_id == LegalKbDocument.document_id,
        )
        .where(
            LegalKbRelation.target_document_id == document_id,
            LegalKbRelation.relation_type.in_(("replaces", "annuls")),
            LegalKbRevision.review_status == "approved",
            LegalKbRevision.publication_status.in_(("published", "suspended", "archived")),
        )
        .order_by(LegalKbRevision.created_at.desc())
    )
    rows = (await db_session.execute(stmt)).all()
    for relation, document, source_url in rows:
        review_status = str((relation.metadata_json or {}).get("review_status") or "needs_review")
        if review_status != "approved":
            continue
        return _LegalKbDocumentBundle(document=document, source_url=source_url)
    return None


def _replacement_label(bundle: _LegalKbDocumentBundle | None) -> str | None:
    if bundle is None:
        return None
    number = bundle.document.document_number or bundle.document.document_id
    title = bundle.document.title or "chua ro tieu de"
    return f"{number} - {title}"


def _historical_reference_from_bundle(
    bundle: _LegalKbDocumentBundle | None,
    *,
    replaced_by: str | None = None,
) -> dict | None:
    if bundle is None:
        return None
    document = bundle.document
    return {
        "document_id": document.document_id,
        "title": document.title,
        "article_num": None,
        "clause_num": None,
        "point_num": None,
        "effective_from": document.effective_date,
        "effective_to": document.expiry_date,
        "status": document.legal_status,
        "replaced_by": replaced_by,
    }


def _historical_reference_from_chunk(
    chunk,
    *,
    replaced_by: str | None = None,
) -> dict:
    return {
        "document_id": chunk.doc_id,
        "title": chunk.doc_title,
        "article_num": chunk.article_num,
        "clause_num": chunk.clause_num,
        "point_num": chunk.point_num,
        "effective_from": chunk.effective_date,
        "effective_to": getattr(chunk, "expiry_date", None),
        "status": chunk.status,
        "replaced_by": replaced_by,
    }


async def _historical_periods_for_documents(
    db_session,
    *,
    document_ids: tuple[str, ...] | None,
) -> list[tuple[date | None, date | None]]:
    if not hasattr(db_session, "execute"):
        return []
    stmt = (
        select(
            LegalKbRetrievalUnit.effective_from,
            LegalKbRetrievalUnit.effective_to,
        )
        .join(
            LegalKbRevision,
            LegalKbRevision.revision_id == LegalKbRetrievalUnit.revision_id,
        )
        .where(
            LegalKbRevision.review_status == "approved",
            LegalKbRevision.publication_status.in_(("published", "suspended", "archived")),
            LegalKbRetrievalUnit.answerable_status == "historical",
        )
        .distinct()
        .order_by(LegalKbRetrievalUnit.effective_from.asc(), LegalKbRetrievalUnit.effective_to.asc())
    )
    if document_ids:
        stmt = stmt.where(LegalKbRetrievalUnit.document_id.in_(document_ids))
    return list((await db_session.execute(stmt)).all())


def _representative_historical_date(period: tuple[date | None, date | None]) -> date:
    effective_from, effective_to = period
    if effective_from is not None:
        return effective_from
    if effective_to is not None:
        return effective_to - timedelta(days=1)
    return date.today()


def _historical_period_clarification_response(periods: list[tuple[date | None, date | None]]) -> str:
    rendered: list[str] = []
    for effective_from, effective_to in periods[:4]:
        if effective_from and effective_to:
            rendered.append(
                f"tu {_format_vi_date(effective_from)} den {_format_vi_date(effective_to - timedelta(days=1))}"
            )
        elif effective_from:
            rendered.append(f"tu {_format_vi_date(effective_from)}")
        elif effective_to:
            rendered.append(f"truoc {_format_vi_date(effective_to)}")
    return (
        "Toi thay van ban nay co nhieu giai doan lich su khac nhau: "
        f"{', '.join(rendered)}. "
        "Ban vui long noi ro moc thoi gian ban muon tra.\n\n"
        f"{LEGAL_DISCLAIMER}"
    )


def _legal_kb_historical_lookup_response(
    query: str,
    chunks,
    *,
    query_date: date,
) -> str:
    if not chunks:
        return (
            "Toi chua tim thay can cu lich su duoc cong bo phu hop voi moc thoi gian ban dang hoi. "
            "Ban co the noi ro ngay ap dung hoac so hieu van ban can tra."
        )
    lead = chunks[0]
    locator = _display_locator(lead.locator_label or "mục liên quan")
    doc_label = lead.document_number or lead.doc_title or "van ban dang duoc hoi"
    snippet = _short_snippet(lead.text_snippet, limit=320)
    return (
        f"Theo dữ liệu lịch sử áp dụng tại ngày {_format_vi_date(query_date)}, "
        f"{doc_label} tại {locator} quy định: {snippet}\n\n"
        "Thông tin này chỉ để tham chiếu lịch sử, không phải căn cứ pháp lý hiện hành."
    )


def _legal_kb_lifecycle_response(
    bundle: _LegalKbDocumentBundle,
    *,
    replacement_bundle: _LegalKbDocumentBundle | None = None,
) -> str:
    document = bundle.document
    parts = [
        f"Van ban so hieu {document.document_number or document.document_id} hien {_legal_status_label(document.legal_status)}.",
        f"Ngay co hieu luc: {_format_vi_date(document.effective_date)}.",
    ]
    if document.expiry_date is not None:
        parts.append(f"Ngay het hieu luc: {_format_vi_date(document.expiry_date)}.")
    if document.title:
        parts.append(f"Ten van ban: {document.title}.")
    replacement_label = _replacement_label(replacement_bundle)
    if replacement_label:
        parts.append(f"Van ban lien quan thay the/annul neu co can cu: {replacement_label}.")
    return " ".join(parts)


async def _legal_kb_document_lookup_response(db_session, document_number: str) -> str | None:
    bundle = await _get_legal_kb_published_document_bundle_by_number(db_session, document_number)
    if bundle is None:
        return None
    document = bundle.document

    summary = await _legal_kb_standard_summary_response(db_session, document_number)
    summary_excerpt = (summary or "").strip()
    if len(summary_excerpt) > 700:
        summary_excerpt = f"{summary_excerpt[:697].rstrip()}..."

    parts = [
        f"Văn bản số hiệu {document.document_number or document_number} có tiêu đề \"{document.title or 'chưa rõ tiêu đề'}\".",
        f"Đây là {_document_type_label(document.document_type)} do {document.issuing_authority or 'chưa rõ cơ quan ban hành'} ban hành.",
        f"Tình trạng hiện tại: {_legal_status_label(document.legal_status)}. Ngày có hiệu lực: {_format_vi_date(document.effective_date)}.",
    ]
    if document.expiry_date is not None:
        parts.append(f"Ngày hết hiệu lực: {_format_vi_date(document.expiry_date)}.")
    if summary_excerpt:
        parts.append(f"Tóm tắt ngắn gọn: {summary_excerpt}")
    else:
        parts.append("Hiện văn bản này chưa có bản tóm tắt chuẩn đã duyệt.")
    return "\n\n".join(parts)


async def _legal_kb_effective_status_response(db_session, document_number: str) -> str | None:
    bundle = await _get_legal_kb_published_document_bundle_by_number(db_session, document_number)
    if bundle is None:
        return None
    document = bundle.document

    parts = [
        f"Văn bản số hiệu {document.document_number or document_number} hiện {_legal_status_label(document.legal_status)}.",
        f"Ngày có hiệu lực: {_format_vi_date(document.effective_date)}.",
    ]
    if document.expiry_date is not None:
        parts.append(f"Ngày hết hiệu lực: {_format_vi_date(document.expiry_date)}.")
    if document.title:
        parts.append(f"Tên văn bản: {document.title}.")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Node 1: Parse & normalize user query
# --------------------------------------------------------------------------- #
async def parse_query(state: AgentState, config: RunnableConfig) -> dict:
    """Normalize deterministically and extract an optional legal query date."""
    query = state.get("query", "").strip()
    normalized = re.sub(r"\s+", " ", query)
    intent = classify_query_intent(query)
    temporal = resolve_query_date(query, today=date.today())
    input_guard = evaluate_input_guardrail(query, query_intent=intent.query_intent)
    conversation_context = state.get("conversation_context") or ""
    follow_up = resolve_follow_up(
        query=normalized,
        query_intent=intent.query_intent,
        conversation_context=conversation_context,
    )
    result = {
        "normalized_query": normalized,
        "retrieval_query": follow_up.retrieval_query,
        "query_intent": intent.query_intent,
        "query_document_number": intent.document_number,
        "query_date": temporal.query_date,
        "query_has_explicit_date": temporal.has_explicit_date,
        "follow_up_used": follow_up.used_history,
        "follow_up_confidence": follow_up.confidence,
        "follow_up_reason": follow_up.reason,
        "injection_detected": input_guard.reason == "prompt_injection",
        "guardrail_triggered": not input_guard.allowed,
        "guardrail_stage": input_guard.stage,
        "guardrail_reason": input_guard.reason,
        "final_response": input_guard.safe_response,
        "temporal_notice": None,
        "knowledge_base": "legal_kb",
    }
    if follow_up.needs_clarification and not result["guardrail_triggered"]:
        result.update(
            {
                "guardrail_triggered": True,
                "guardrail_stage": "input",
                "guardrail_reason": "query_clarification",
                "final_response": QUERY_CLARIFICATION_TEMPLATE,
            }
        )
    elif (
        intent.query_intent == "ambiguous"
        and not result["guardrail_triggered"]
        and not conversation_context
    ):
        result.update(
            {
                "guardrail_triggered": True,
                "guardrail_stage": "input",
                "guardrail_reason": "query_clarification",
                "final_response": QUERY_CLARIFICATION_TEMPLATE,
            }
        )
    if temporal.needs_clarification:
        result.update(
            {
                "guardrail_triggered": True,
                "guardrail_stage": "input",
                "guardrail_reason": "temporal_clarification",
                "final_response": temporal.clarification_response,
            }
        )
    return result


# --------------------------------------------------------------------------- #
# Node 2: Scope classification (spec 11 sect3)
# --------------------------------------------------------------------------- #
async def scope_classify(
    state: AgentState,
) -> Command[Literal["deflect", "hybrid_retrieve"]]:
    """Classify scope using fast embedding cosine; route out-of-scope to deflect."""
    query = (
        state.get("retrieval_query")
        if state.get("follow_up_used")
        else state.get("normalized_query") or state.get("query", "")
    )

    if (
        state.get("guardrail_triggered")
        and state.get("guardrail_stage") == "input"
        and state.get("guardrail_reason") in _DIRECT_INPUT_RESPONSE_REASONS
    ):
        return Command(
            update={
                "scope_result": ScopeResult(label=ScopeLabel.uncertain, score=0.0),
                "is_out_of_scope": False,
            },
            goto="deflect",
        )

    if is_small_talk_query(query):
        return Command(
            update={
                "scope_result": ScopeResult(label=ScopeLabel.uncertain, score=0.0),
                "is_out_of_scope": False,
                "final_response": SMALL_TALK_TEMPLATE,
                "guardrail_triggered": False,
                "guardrail_stage": None,
                "guardrail_reason": None,
            },
            goto="deflect",
        )

    if semantic_document_scope_numbers(query):
        return Command(
            update={"scope_result": ScopeResult(label=ScopeLabel.in_scope, score=1.0)},
            goto="hybrid_retrieve",
        )

    scope: ScopeResult = await classify_scope(query)

    if scope.label == ScopeLabel.out_of_scope:
        return Command(
            update={
                "scope_result": scope,
                "is_out_of_scope": True,
                "final_response": OUT_OF_SCOPE_TEMPLATE,
                "guardrail_triggered": True,
                "guardrail_stage": "input",
                "guardrail_reason": "out_of_scope",
            },
            goto="deflect",
        )
    return Command(update={"scope_result": scope}, goto="hybrid_retrieve")


# --------------------------------------------------------------------------- #
# Node 3: Deflect
# --------------------------------------------------------------------------- #
async def deflect(state: AgentState) -> dict:
    """Return a direct response for out-of-scope, injection, or harmless small talk."""
    response = state.get("final_response", OUT_OF_SCOPE_TEMPLATE)
    if response != SMALL_TALK_TEMPLATE and LEGAL_DISCLAIMER not in response:
        if "LƯU Ý PHÁP LÝ:" in response:
            response = response.split("LƯU Ý PHÁP LÝ:")[0].strip()
        response = f"{response}\n\n{LEGAL_DISCLAIMER}"
    return {
        "final_response": response,
        "disclaimer_appended": LEGAL_DISCLAIMER in response,
    }


# --------------------------------------------------------------------------- #
# Node 4: Hybrid retrieval (PRD F02 — active filter mandatory)
# --------------------------------------------------------------------------- #
async def hybrid_retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    """Run hybrid vector + FTS retrieval. db_session injected via config."""
    query = state.get("retrieval_query") or state.get("normalized_query") or state.get("query", "")
    current_query = state.get("normalized_query") or state.get("query") or query
    legal_kb_query = current_query if _DOC_NUMBER_QUERY_PATTERN.search(current_query) else query
    db_session = (config.get("configurable") or {}).get("db_session")

    if db_session is None:
        logger.error("hybrid_retrieve_node: db_session missing in config['configurable']")
        return {"retrieved_contexts": [], "status_filter": "active", "repealed_notice": None}

    explicit_document_number = state.get("query_document_number") or _explicit_document_number(
        legal_kb_query
    )
    explicit_document_ids = (
        await _document_ids_for_explicit_refs(db_session, legal_kb_query)
        if explicit_document_number
        else None
    )
    # Topic hints may improve ranking, but must not exclude amendments/new sources.
    scoped_document_ids = explicit_document_ids
    if explicit_document_number and explicit_document_ids == ():
        return {
            "retrieved_contexts": [],
            "status_filter": "active",
            "repealed_notice": None,
            "guardrail_triggered": True,
            "guardrail_stage": "retrieval",
            "guardrail_reason": _DOC_NOT_FOUND_GUARDRAIL_REASON,
            "final_response": _legal_kb_document_not_found_response(explicit_document_number),
        }

    if state.get("query_intent") == "effective_status" and explicit_document_number:
        source_bundle = await _get_legal_kb_published_document_bundle_by_number(
            db_session,
            explicit_document_number,
        )
        effective_status_response = await _legal_kb_effective_status_response(
            db_session,
            explicit_document_number,
        )
        if effective_status_response is not None:
            return {
                "retrieved_contexts": [],
                "status_filter": "active",
                "repealed_notice": None,
                "guardrail_triggered": True,
                "guardrail_stage": "retrieval",
                "guardrail_reason": _EFFECTIVE_STATUS_GUARDRAIL_REASON,
                "final_response": effective_status_response,
                "response_document_sources": (
                    [_document_source_from_bundle(source_bundle)] if source_bundle is not None else []
                ),
                "response_historical_references": [],
            }

        lifecycle_bundle = await _get_legal_kb_lifecycle_document_bundle_by_number(
            db_session,
            explicit_document_number,
        )
        if lifecycle_bundle is not None:
            replacement_bundle = await _find_replacement_bundle_for_document(
                db_session,
                lifecycle_bundle.document.document_id,
            )
            historical_reference = _historical_reference_from_bundle(
                lifecycle_bundle,
                replaced_by=_replacement_label(replacement_bundle),
            )
            return {
                "retrieved_contexts": [],
                "status_filter": "historical",
                "repealed_notice": None,
                "guardrail_triggered": True,
                "guardrail_stage": "retrieval",
                "guardrail_reason": _EFFECTIVE_STATUS_GUARDRAIL_REASON,
                "final_response": _legal_kb_lifecycle_response(
                    lifecycle_bundle,
                    replacement_bundle=replacement_bundle,
                ),
                "response_document_sources": [
                    source
                    for source in [_document_source_from_bundle(lifecycle_bundle)]
                    if source is not None
                ],
                "response_historical_references": (
                    [historical_reference] if historical_reference is not None else []
                ),
            }

        return {
            "retrieved_contexts": [],
            "status_filter": "active",
            "repealed_notice": None,
            "guardrail_triggered": True,
            "guardrail_stage": "retrieval",
            "guardrail_reason": _EFFECTIVE_STATUS_GUARDRAIL_REASON,
            "final_response": _legal_kb_document_not_found_response(explicit_document_number),
            "response_document_sources": [],
            "response_historical_references": [],
        }

    if state.get("query_intent") == "document_lookup" and explicit_document_number:
        source_bundle = await _get_legal_kb_published_document_bundle_by_number(
            db_session,
            explicit_document_number,
        )
        document_lookup_response = await _legal_kb_document_lookup_response(
            db_session,
            explicit_document_number,
        )
        return {
            "retrieved_contexts": [],
            "status_filter": "active",
            "repealed_notice": None,
            "guardrail_triggered": True,
            "guardrail_stage": "retrieval",
            "guardrail_reason": _DOC_LOOKUP_GUARDRAIL_REASON,
            "final_response": document_lookup_response
            or _legal_kb_document_not_found_response(explicit_document_number),
            "response_document_sources": (
                [_document_source_from_bundle(source_bundle)] if source_bundle is not None else []
            ),
        }

    summary_document_number = _summary_document_number(legal_kb_query)
    summary_response, summary_document_source = await _legal_kb_standard_summary_bundle(
        db_session,
        legal_kb_query,
    )
    if summary_response or summary_document_number:
        return {
            "retrieved_contexts": [],
            "status_filter": "active",
            "repealed_notice": None,
            "guardrail_triggered": True,
            "guardrail_stage": "retrieval",
            "guardrail_reason": _SUMMARY_GUARDRAIL_REASON,
            "final_response": summary_response
            or _legal_kb_summary_missing_response(summary_document_number),
            "response_document_sources": (
                [summary_document_source] if summary_document_source is not None else []
            ),
        }

    if state.get("query_intent") == "comparison_history":
        historical_query_date = state.get("query_date") or date.today()
        if not state.get("query_has_explicit_date") and scoped_document_ids:
            periods = await _historical_periods_for_documents(
                db_session,
                document_ids=scoped_document_ids,
            )
            if len(periods) > 1:
                return {
                    "retrieved_contexts": [],
                    "status_filter": "historical",
                    "repealed_notice": None,
                    "guardrail_triggered": True,
                    "guardrail_stage": "retrieval",
                    "guardrail_reason": "temporal_clarification",
                    "final_response": _historical_period_clarification_response(periods),
                    "response_document_sources": [],
                    "response_historical_references": [],
                }
            if len(periods) == 1:
                historical_query_date = _representative_historical_date(periods[0])

        query_embedding = await embed_query(expand_query_for_retrieval(legal_kb_query))
        retrieval = await hybrid_retrieve_legal(
            db_session,
            legal_kb_query,
            query_embedding,
            query_date=historical_query_date,
            document_ids=scoped_document_ids,
            mode="historical",
        )
        chunks = retrieval.chunks
        if chunks:
            historical_references = [
                _historical_reference_from_chunk(chunk) for chunk in chunks[:8]
            ]
            return {
                "retrieved_contexts": chunks,
                "status_filter": "historical",
                "repealed_notice": None,
                "query_date": historical_query_date,
                "guardrail_triggered": True,
                "guardrail_stage": "retrieval",
                "guardrail_reason": _HISTORICAL_LOOKUP_GUARDRAIL_REASON,
                "final_response": _legal_kb_historical_lookup_response(
                    legal_kb_query,
                    chunks,
                    query_date=historical_query_date,
                ),
                "response_document_sources": [],
                "response_historical_references": historical_references,
            }
        return {
            "retrieved_contexts": [],
            "status_filter": "historical",
            "repealed_notice": None,
            "query_date": historical_query_date,
            "response_document_sources": [],
            "response_historical_references": [],
        }

    retrieval_query = legal_kb_query
    expanded_retrieval_query = expand_query_for_retrieval(retrieval_query)
    query_embedding = await embed_query(expanded_retrieval_query)
    retrieval = await hybrid_retrieve_legal(
        db_session,
        expanded_retrieval_query,
        query_embedding,
        query_date=state.get("query_date") or date.today(),
        document_ids=scoped_document_ids,
    )
    chunks = retrieval.chunks

    result = {
        "retrieved_contexts": chunks,
        "status_filter": "active",
        "repealed_notice": None,
    }
    if not chunks:
        future_notice = await future_effective_notice_for_query(
            db_session,
            query=retrieval_query,
            reference_date=state.get("query_date") or date.today(),
        )
        if future_notice:
            result.update(
                {
                    "temporal_notice": future_notice,
                    "guardrail_triggered": True,
                    "guardrail_stage": "retrieval",
                    "guardrail_reason": "future_effective",
                    "final_response": future_notice,
                }
            )
    return result


async def hybrid_retrieve(state: AgentState, config: RunnableConfig) -> dict:
    """Backward-compatible alias for older tests and patches."""
    return await hybrid_retrieve_node(state, config)


# --------------------------------------------------------------------------- #
# Node 5: Local legal ranking (spec 11 sect5)
# --------------------------------------------------------------------------- #
async def rerank_node(state: AgentState) -> dict:
    """Apply deterministic local legal ranking and pack diverse context."""
    if state.get("guardrail_reason") == _HISTORICAL_LOOKUP_GUARDRAIL_REASON:
        return {
            "reranker_failed": False,
            "reranker_used": False,
            "reranker_error_code": None,
            "low_confidence": False,
            "retrieval_candidate_count": len(state.get("retrieved_contexts", [])),
            "rerank_top_score": None,
            "evidence_policy_notice": None,
        }
    query = state.get("normalized_query") or state.get("query", "")
    chunks = state.get("retrieved_contexts", [])
    if not chunks:
        return {
            "reranker_failed": False,
            "reranker_used": False,
            "reranker_error_code": None,
            "low_confidence": True,
            "retrieval_candidate_count": 0,
            "rerank_top_score": None,
            "evidence_policy_notice": None,
        }

    rank_query = expand_query_for_retrieval(query_for_local_ranking(query))
    result = await rerank_chunks(rank_query, chunks)
    packed_chunks = pack_context(result.chunks)
    policy = evaluate_evidence_policy(
        query_text=query,
        query_intent=state.get("query_intent"),
        chunks=packed_chunks,
    )
    response: dict = {
        "retrieved_contexts": packed_chunks,
        "reranker_failed": result.reranker_failed,
        "reranker_used": result.reranker_used,
        "reranker_error_code": result.error_code,
        "low_confidence": result.low_confidence,
        "retrieval_candidate_count": len(chunks),
        "rerank_top_score": result.top_score,
        "evidence_policy_notice": policy.prompt_notice,
    }
    if policy.document_sources is not None:
        response["response_document_sources"] = policy.document_sources
    if policy.is_direct_response:
        response.update(
            {
                "guardrail_triggered": True,
                "guardrail_stage": "rerank",
                "guardrail_reason": policy.guardrail_reason,
                "final_response": policy.final_response,
                "verified_citations": [],
            }
        )
    return response


# --------------------------------------------------------------------------- #
# Node 6: LLM generation (spec 13 sect2-4)
# --------------------------------------------------------------------------- #
async def llm_generate(state: AgentState, config: RunnableConfig) -> dict:
    """Call the LLM. llm instance injected via config['configurable']['llm']."""
    llm = (config.get("configurable") or {}).get("llm")
    db_session = (config.get("configurable") or {}).get("db_session")
    query = state.get("normalized_query") or state.get("query", "")
    chunks = state.get("retrieved_contexts", [])
    low_confidence = state.get("low_confidence", False)
    repealed_notice = state.get("repealed_notice") or ""

    if state.get("guardrail_reason") in {
        "temporal_clarification",
        "future_effective",
        _DOC_NOT_FOUND_GUARDRAIL_REASON,
        _DOC_LOOKUP_GUARDRAIL_REASON,
        _EFFECTIVE_STATUS_GUARDRAIL_REASON,
        _HISTORICAL_LOOKUP_GUARDRAIL_REASON,
        _SUMMARY_GUARDRAIL_REASON,
        _EVIDENCE_CLARIFICATION_GUARDRAIL_REASON,
        _EVIDENCE_MULTIPLE_GUARDRAIL_REASON,
        _EVIDENCE_INSUFFICIENT_GUARDRAIL_REASON,
    }:
        return {"llm_output": state.get("final_response") or ""}

    if not chunks or llm is None or low_confidence:
        return {"llm_output": INSUFFICIENT_CONTEXT_TEMPLATE}

    if not state.get("evidence_policy_notice") and hasattr(db_session, "execute"):
        return {"llm_output": _structured_retrieval_answer(chunks)}

    evidence_notices = [
        state.get("evidence_policy_notice") or "",
    ]
    if db_session is not None and chunks:
        document_ids = tuple(sorted({chunk.doc_id for chunk in chunks if chunk.doc_id}))
        evidence = await assemble_evidence_bundle(
            db_session,
            query_date=state.get("query_date") or date.today(),
            document_ids=document_ids or None,
        )
        if evidence.has_conflict and evidence.prompt_notice:
            evidence_notices.append(evidence.prompt_notice)
    evidence_notice = "\n\n".join(part for part in evidence_notices if part)

    if not evidence_notice:
        return {"llm_output": _structured_retrieval_answer(chunks)}

    legal_notice = "\n\n".join(part for part in (repealed_notice, evidence_notice) if part)

    prompt = format_rag_prompt(
        user_query=query,
        context=format_context(chunks),
        current_date=(state.get("query_date") or date.today()).isoformat(),
        repealed_notice=legal_notice,
        query_intent=state.get("query_intent"),
        conversation_context=state.get("conversation_context") or "Không có nội dung trước đó.",
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    response = await llm.ainvoke(messages, max_tokens=500)
    content = response.content if hasattr(response, "content") else str(response)
    return {
        "llm_output": _clean_llm_output(content),
        "evidence_notice": evidence_notices[-1] if len(evidence_notices) > 1 else None,
    }


def _clean_llm_output(content: str) -> str:
    """Remove internal prompt labels if a model echoes them despite instructions."""
    hidden_label = re.compile(
        r"^\s*(?:\[(?:block|warn|cảnh báo hiệu lực[^\]]*|citation verification[^\]]*)\]"
        r"|citation verification\s*:\s*.*)$",
        re.IGNORECASE,
    )
    lines = [line for line in content.splitlines() if not hidden_label.match(line)]
    cleaned = "\n".join(lines).replace("CONTEXT", "dữ liệu tra cứu")
    return re.sub(r"[\[(]SOURCE\s+chunk_id=[^\])]+[\])]", "", cleaned, flags=re.IGNORECASE).strip()


# --------------------------------------------------------------------------- #
# Node 7: Citation verification (spec 12)
# --------------------------------------------------------------------------- #
_CITATION_LOOKUP_PHRASES = (
    "can cu",
    "can cu nao",
    "dan can cu",
    "dan quy dinh",
    "dan dung van ban",
    "vien dan",
)


def _normalize_agent_text(text: str) -> str:
    lowered = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    normalized = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9/]+", " ", normalized).strip()


def _is_citation_lookup_query(query: str) -> bool:
    normalized = f" {_normalize_agent_text(query)} "
    return any(f" {phrase} " in normalized for phrase in _CITATION_LOOKUP_PHRASES)


def _citation_lookup_answer(citations: list) -> str:
    if not citations:
        return INSUFFICIENT_CONTEXT_TEMPLATE
    primary = citations[0]
    locator = primary.locator_label or (
        f"Điều {primary.article_num}"
        if primary.article_num is not None
        else "đơn vị dữ liệu được truy xuất"
    )
    document = primary.doc_title
    return (
        "Căn cứ phù hợp nhất trong kho dữ liệu hiện hành là "
        f"{locator} của {document}. "
        "Tôi đã gắn trích dẫn có cấu trúc từ dữ liệu truy xuất để bạn kiểm tra ở phần căn cứ."
    )


def _retrieval_fallback_answer(citations: list) -> str:
    if not citations:
        return INSUFFICIENT_CONTEXT_TEMPLATE
    primary = citations[0]
    locator = primary.locator_label or (
        f"Điều {primary.article_num}"
        if primary.article_num is not None
        else "căn cứ được truy xuất"
    )
    document = primary.doc_title
    return (
        "Tôi tìm thấy căn cứ liên quan trong kho dữ liệu hiện hành: "
        f"{locator} của {document}. "
        "Bạn có thể xem phần căn cứ kèm theo để đối chiếu nội dung chi tiết."
    )


def _short_snippet(text: str | None, *, limit: int = 260) -> str:
    snippet = re.sub(r"\s+", " ", (text or "").strip())
    content_match = re.search(r"(?:Nội dung|Noi dung)\s*:\s*(.+)$", snippet)
    if content_match:
        snippet = content_match.group(1).strip()
    snippet = re.sub(
        r"\b(?:Tieu de|Tiêu đề|Loai van ban|Loại văn bản|Co quan ban hanh|Cơ quan ban hành|Hieu luc tu|Hiệu lực từ|Trich dan|Trích dẫn)\s*:\s*",
        "",
        snippet,
    )
    snippet = re.sub(r"\bATKT\b", "an toàn kỹ thuật", snippet)
    snippet = re.sub(r"\bBVMT\b", "bảo vệ môi trường", snippet)
    if len(snippet) <= limit:
        return snippet
    clipped = snippet[: limit - 3].rstrip()
    last_space = clipped.rfind(" ")
    if last_space >= max(40, int(limit * 0.65)):
        clipped = clipped[:last_space].rstrip(" ,;:")
    return f"{clipped}..."


def _display_locator(label: str | None) -> str:
    if not label:
        return "căn cứ liên quan"
    replacements = {
        "Chuong": "Chương",
        "Dieu": "Điều",
        "khoan": "khoản",
        "diem": "điểm",
    }
    result = label
    for source, target in replacements.items():
        result = re.sub(rf"\b{source}\b", target, result, flags=re.IGNORECASE)
    return result


def _structured_retrieval_answer(chunks) -> str:
    grouped: dict[str, object] = {}
    for chunk in chunks:
        if not chunk.doc_id or not chunk.chunk_id or chunk.status != "active":
            continue
        grouped.setdefault(chunk.chunk_id, chunk)
        if len(grouped) >= 5:
            break
    if not grouped:
        return INSUFFICIENT_CONTEXT_TEMPLATE

    parts = ["Tôi tìm thấy các đoạn quy định liên quan dưới đây. Đây là trích nội dung nguồn để bạn đối chiếu; việc áp dụng còn phụ thuộc tình huống cụ thể."]
    for chunk in grouped.values():
        text = chunk.full_text or chunk.text_snippet
        body = re.split(r"(?:Nội dung|Noi dung)\s*:\s*", text, maxsplit=1)[-1].strip()
        locator = chunk.locator_label
        if not locator and chunk.article_num is not None:
            locator = f"Điều {chunk.article_num}"
            if chunk.clause_num is not None:
                locator += f", khoản {chunk.clause_num}"
            if chunk.point_num:
                locator += f", điểm {chunk.point_num}"
        parts.append(f"**{_display_locator(locator)} — {chunk.doc_title}**\n\n{body}")
    return "\n\n".join(parts)


async def verify_citation_node(state: AgentState) -> dict:
    answer = state.get("llm_output") or ""
    chunks = state.get("retrieved_contexts", [])
    # Only the exact server-rendered evidence excerpt can use metadata citations.
    # A model-written prefix is never proof that the answer came from a source.
    if chunks and answer == _structured_retrieval_answer(chunks):
        citations = citations_from_retrieval_units(chunks, max_citations=5)
        return {
            "llm_output": answer,
            "verified_citations": citations,
            "faithfulness_score": 1.0 if citations else 0.0,
            "has_hallucination": False,
        }
    if state.get("guardrail_reason") in _DIRECT_EVIDENCE_GUARDRAIL_REASONS:
        return {
            "llm_output": answer,
            "verified_citations": [],
            "faithfulness_score": 0.0,
            "has_hallucination": False,
        }
    checked_citations = verify_citations(answer, chunks)
    if has_hallucination(checked_citations):
        # An unsupported introduction can survive line pruning; reject the whole
        # generated answer rather than keeping unverified uncited remnants.
        return {"llm_output": "", "verified_citations": [],
                "faithfulness_score": 0.0, "has_hallucination": True}
    citations = [
        citation
        for citation in checked_citations
        if citation.doc_id
        and citation.chunk_id
        and citation.status == "active"
        and citation.verification_status
        in {VerificationStatus.verified, VerificationStatus.partial}
    ]
    is_citation_lookup = _is_citation_lookup_query(state.get("query") or "")
    if (
        not citations
        and chunks
        and state.get("guardrail_reason") not in _DIRECT_EVIDENCE_GUARDRAIL_REASONS
        and is_citation_lookup
        and not checked_citations
        and "chưa tìm thấy căn cứ đủ chắc" in answer.lower()
    ):
        citations = citations_from_retrieval_units(chunks)
        checked_citations = citations
        if is_citation_lookup and citations:
            answer = _citation_lookup_answer(citations)
        elif citations and (
            not answer.strip()
            or "chưa tìm thấy căn cứ đủ chắc" in answer.lower()
        ):
            answer = _retrieval_fallback_answer(citations)
    return {
        "llm_output": answer,
        "verified_citations": citations,
        "faithfulness_score": compute_faithfulness_score(checked_citations),
        "has_hallucination": has_hallucination(checked_citations),
    }


# --------------------------------------------------------------------------- #
# Node 8: Output guardrail
# --------------------------------------------------------------------------- #
async def output_guardrail_node(state: AgentState) -> dict:
    """Block unsafe generated legal answers before final disclaimer injection."""
    if state.get("guardrail_reason") in {
        "temporal_clarification",
        "future_effective",
        _DOC_NOT_FOUND_GUARDRAIL_REASON,
        _DOC_LOOKUP_GUARDRAIL_REASON,
        _EFFECTIVE_STATUS_GUARDRAIL_REASON,
        _HISTORICAL_LOOKUP_GUARDRAIL_REASON,
        _SUMMARY_GUARDRAIL_REASON,
        _EVIDENCE_CLARIFICATION_GUARDRAIL_REASON,
        _EVIDENCE_MULTIPLE_GUARDRAIL_REASON,
        _EVIDENCE_INSUFFICIENT_GUARDRAIL_REASON,
    } and state.get(
        "final_response"
    ):
        return {
            "guardrail_triggered": True,
            "guardrail_stage": state.get("guardrail_stage"),
            "guardrail_reason": state.get("guardrail_reason"),
        }
    decision = evaluate_output_guardrail(
        answer=state.get("llm_output") or "",
        citations=state.get("verified_citations", []),
        has_hallucination=state.get("has_hallucination", False),
        low_confidence=state.get("low_confidence", False),
        faithfulness_score=state.get("faithfulness_score"),
    )
    if decision.allowed:
        return {
            "guardrail_triggered": False,
            "guardrail_stage": None,
            "guardrail_reason": None,
        }

    return {
        "final_response": decision.safe_response,
        "verified_citations": [],
        "guardrail_triggered": True,
        "guardrail_stage": decision.stage,
        "guardrail_reason": decision.reason,
    }


# --------------------------------------------------------------------------- #
# Node 9: Disclaimer injection (PRD F05 — 100% mandatory)
# --------------------------------------------------------------------------- #
async def inject_disclaimer(state: AgentState) -> dict:
    """Append disclaimer unconditionally to every response."""
    if state.get("is_out_of_scope") or state.get("guardrail_triggered"):
        response = state.get("final_response") or OUT_OF_SCOPE_TEMPLATE
        if LEGAL_DISCLAIMER not in response:
            if "LƯU Ý PHÁP LÝ:" in response:
                response = response.split("LƯU Ý PHÁP LÝ:")[0].strip()
            response = f"{response}\n\n{LEGAL_DISCLAIMER}"
        return {"final_response": response, "disclaimer_appended": True}

    answer = state.get("llm_output") or ""
    citations = state.get("verified_citations", [])
    if not answer:
        return {"disclaimer_appended": False}

    has_supported_citation = any(
        citation.verification_status.value in {"verified", "partial"} for citation in citations
    )
    if (
        state.get("has_hallucination")
        or not citations
        or (citations and not has_supported_citation)
    ):
        answer = INSUFFICIENT_CONTEXT_TEMPLATE

    if LEGAL_DISCLAIMER not in answer:
        if "LƯU Ý PHÁP LÝ:" in answer:
            answer = answer.split("LƯU Ý PHÁP LÝ:")[0].strip()
        evidence_notice = state.get("evidence_notice")
        if evidence_notice:
            answer = f"{evidence_notice}\n\n{answer}"
        answer = f"{answer}\n\n{LEGAL_DISCLAIMER}"
    return {"final_response": answer, "disclaimer_appended": True}


__all__ = [
    "deflect",
    "hybrid_retrieve",
    "hybrid_retrieve_node",
    "inject_disclaimer",
    "llm_generate",
    "output_guardrail_node",
    "parse_query",
    "rerank_node",
    "scope_classify",
    "verify_citation_node",
]
