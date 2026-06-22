"""Agent state schema for the LangGraph RAG agent (spec 09, 13; api 04 sect3.1).

Defines the full state carried through the graph: from raw user query through
scope classification, retrieval, local ranking, LLM generation, citation verification,
and disclaimer injection.
"""

from __future__ import annotations

from datetime import date

from typing_extensions import TypedDict

from src.schemas.rag import Citation, RetrievedChunk, ScopeResult


class AgentState(TypedDict):
    """Complete state for the Legal Q&A RAG agent.

    Fields are deliberately optional where not guaranteed (e.g. scope_result
    may be None before the scope node runs). Messages from MessagesState carry
    the conversation history.
    """

    # --- Query ---
    query: str
    normalized_query: str | None
    retrieval_query: str | None
    query_intent: str | None
    query_document_number: str | None
    query_date: date | None
    query_has_explicit_date: bool
    conversation_context: str | None
    follow_up_used: bool
    follow_up_confidence: float | None
    follow_up_reason: str | None

    # --- Scope ---
    scope_result: ScopeResult | None

    # --- Retrieval ---
    status_filter: str  # "active" by default; "historical" only on dedicated history paths
    retrieved_contexts: list[RetrievedChunk]
    reranker_failed: bool  # retained in API metadata; local ranker does not fail externally
    reranker_used: bool
    reranker_error_code: str | None
    low_confidence: bool
    retrieval_candidate_count: int
    rerank_top_score: float | None

    # --- Generation ---
    llm_output: str | None
    repealed_notice: str | None
    temporal_notice: str | None
    evidence_policy_notice: str | None
    evidence_notice: str | None
    response_document_sources: list[dict]
    response_historical_references: list[dict]

    # --- Verification ---
    verified_citations: list[Citation]
    faithfulness_score: float | None
    has_hallucination: bool

    # --- Disclaimer ---
    disclaimer_appended: bool
    guardrail_triggered: bool
    guardrail_stage: str | None
    guardrail_reason: str | None

    # --- Final ---
    final_response: str | None
    is_out_of_scope: bool
    injection_detected: bool | None
    kb_version: str | None
