"""LangGraph tools for the RAG agent (spec 09, 05).

Tools expose the retrieval pipeline to the graph: hybrid search, scope
classification, validity checking, and citation verification. Each tool
reuses the existing src/rag/ modules so behavior is consistent whether
called from the agent or directly from API routes.
"""

from __future__ import annotations

from datetime import date

from typing_extensions import TypedDict

from src.rag.embedding import embed_query
from src.rag.retrieval.hybrid_v2 import hybrid_retrieve_v2
from src.rag.verification.replacement import find_replacement
from src.schemas.rag import RetrievedChunk


class RetrieverInput(TypedDict):
    query: str


async def legal_retriever(
    query: str,
    db_session,
) -> list[RetrievedChunk]:
    """Run hybrid retrieval on active documents (PRD F02).

    This is the primary RAG tool. It embeds the query, runs vector + FTS
    search with the mandatory active filter, merges results, and returns
    ranked candidates for the local legal-ranking stage.
    """
    query_embedding = await embed_query(query)
    retrieval = await hybrid_retrieve_v2(
        db_session,
        query,
        query_embedding,
        query_date=date.today(),
    )
    return retrieval.chunks


async def validity_checker(
    doc_id: str,
    db_session,
) -> dict:
    """Check a document validity status and find active replacement.

    Walks the replaced_by chain to find an active replacement if the given
    doc is repealed. Returns metadata for the warning banner.
    """
    replacement = await find_replacement(db_session, doc_id)
    return {
        "doc_id": doc_id,
        "has_active_replacement": replacement is not None,
        "replacement_doc_id": replacement.doc_id if replacement else None,
        "replacement_title": replacement.title if replacement else None,
    }


__all__ = [
    "legal_retriever",
    "validity_checker",
]
