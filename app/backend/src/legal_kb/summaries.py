from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.legal_kb.evidence import assemble_evidence_bundle
from src.models.legal_kb import LegalKbRevision, LegalKbSummary
from src.rag.embedding import embed_query
from src.rag.prompts import (
    INSUFFICIENT_CONTEXT_TEMPLATE,
    LEGAL_DISCLAIMER,
    SYSTEM_PROMPT,
    format_rag_prompt,
)
from src.rag.reranking import rerank_chunks
from src.rag.retrieval.context_packer import format_context, pack_context
from src.rag.retrieval.hybrid_legal import (
    future_effective_notice_for_query,
    hybrid_retrieve_legal,
    related_document_ids,
)
from src.rag.retrieval.query_utils import expand_query_for_retrieval, query_for_local_ranking
from src.rag.verification import (
    compute_faithfulness_score,
    has_hallucination,
    verify_citations,
)
from src.schemas.rag import Citation, VerificationStatus


@dataclass(frozen=True)
class DynamicSummaryResult:
    content: str
    citations: list[Citation]
    faithfulness_score: float | None
    summary_type: str = "dynamic"
    related_document_ids: tuple[str, ...] = ()


async def get_standard_summary(
    session: AsyncSession,
    *,
    document_id: str,
) -> LegalKbSummary:
    stmt = (
        select(LegalKbSummary)
        .join(
            LegalKbRevision,
            LegalKbRevision.revision_id == LegalKbSummary.revision_id,
        )
        .where(
            LegalKbSummary.document_id == document_id,
            LegalKbSummary.review_status == "approved",
            LegalKbRevision.publication_status == "published",
        )
        .order_by(LegalKbRevision.created_at.desc())
        .limit(1)
    )
    summary = await session.scalar(stmt)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Khong tim thay standard summary da duoc phe duyet.",
        )
    return summary


async def build_dynamic_summary(
    session: AsyncSession,
    *,
    document_id: str,
    prompt: str,
    query_date: date,
    llm: ChatOpenAI,
) -> DynamicSummaryResult:
    document_scope = await related_document_ids(session, document_id=document_id)
    retrieval_query = expand_query_for_retrieval(prompt)
    query_embedding = await embed_query(retrieval_query)
    retrieval = await hybrid_retrieve_legal(
        session,
        prompt,
        query_embedding,
        query_date=query_date,
        document_ids=document_scope,
    )
    if not retrieval.chunks:
        future_notice = await future_effective_notice_for_query(
            session,
            query=prompt,
            reference_date=query_date,
            document_ids=document_scope,
        )
        content = f"{INSUFFICIENT_CONTEXT_TEMPLATE}\n\n{LEGAL_DISCLAIMER}"
        if future_notice:
            content = f"{future_notice}\n\n{LEGAL_DISCLAIMER}"
        return DynamicSummaryResult(
            content=content,
            citations=[],
            faithfulness_score=None,
            related_document_ids=document_scope,
        )

    reranked = await rerank_chunks(expand_query_for_retrieval(query_for_local_ranking(prompt)), retrieval.chunks)
    if reranked.low_confidence or not reranked.chunks:
        return DynamicSummaryResult(
            content=f"{INSUFFICIENT_CONTEXT_TEMPLATE}\n\n{LEGAL_DISCLAIMER}",
            citations=[],
            faithfulness_score=reranked.top_score,
            related_document_ids=document_scope,
        )

    packed_chunks = pack_context(reranked.chunks)
    evidence = await assemble_evidence_bundle(
        session,
        query_date=query_date,
        document_ids=document_scope,
    )
    evidence_notice = evidence.prompt_notice
    prompt_text = prompt if not evidence_notice else f"{evidence_notice}\n\n{prompt}"
    response = await llm.ainvoke(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": format_rag_prompt(
                    user_query=prompt_text,
                    context=format_context(packed_chunks),
                    current_date=query_date.isoformat(),
                    conversation_context="Khong co noi dung truoc do.",
                    query_intent="document_summary_standard",
                ),
            },
        ],
        max_tokens=500,
    )
    content = response.content if hasattr(response, "content") else str(response)
    citations = [
        citation
        for citation in verify_citations(content, packed_chunks)
        if citation.status == "active"
        and citation.verification_status in {VerificationStatus.verified, VerificationStatus.partial}
    ]
    if not citations or has_hallucination(citations):
        return DynamicSummaryResult(
            content=f"{INSUFFICIENT_CONTEXT_TEMPLATE}\n\n{LEGAL_DISCLAIMER}",
            citations=[],
            faithfulness_score=compute_faithfulness_score(citations),
            related_document_ids=document_scope,
        )
    content = content.strip()
    if evidence.has_conflict:
        content = f"{evidence.prompt_notice}\n\n{content}"
    return DynamicSummaryResult(
        content=f"{content}\n\n{LEGAL_DISCLAIMER}",
        citations=citations,
        faithfulness_score=compute_faithfulness_score(citations),
        related_document_ids=document_scope,
    )
