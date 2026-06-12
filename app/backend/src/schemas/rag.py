"""Pydantic schemas for the RAG pipeline.

Mirrors the JSON contracts in docs/project/11-rag-retrieval-ranking-spec.md and
12-citation-verification-spec.md so retrieval, verification and the API layer
share one set of validated types.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class ScopeLabel(str, Enum):
    in_scope = "in_scope"
    out_of_scope = "out_of_scope"
    uncertain = "uncertain"


class QueryIntent(str, Enum):
    general_legal = "general_legal"
    document_summary_standard = "document_summary_standard"
    document_lookup = "document_lookup"
    effective_status = "effective_status"
    comparison_history = "comparison_history"
    definition = "definition"
    obligation = "obligation"
    penalty = "penalty"
    procedure = "procedure"
    ambiguous = "ambiguous"


class VerificationStatus(str, Enum):
    verified = "verified"
    partial = "partial"
    unverified = "unverified"
    blocked = "blocked"


class ScopeResult(BaseModel):
    """Output of the (non-LLM) scope classifier."""

    label: ScopeLabel
    score: float = Field(ge=0.0, le=1.0)


class ChunkMetadata(BaseModel):
    """Enrichment metadata stored in document_chunks.metadata_json."""

    display_path: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    source_page: int | None = None
    parser_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RetrievedChunk(BaseModel):
    """A candidate chunk returned by retrieval/rerank.

    Matches the on_tool_end HybridRetriever payload in 04-api-spec.md §3.1.
    """

    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str = ""
    document_number: str | None = None
    chunk_type: str
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    locator_type: str | None = None
    locator_label: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_number: str | None = None
    sign_codes: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    corpus: str | None = None
    canonical_provision_id: str | None = None
    status: str
    effective_date: date
    expiry_date: date | None = None
    text_snippet: str
    full_text: str | None = None
    source_url: str | None = None
    # Scores are populated as the candidate moves through the pipeline.
    vector_score: float | None = None
    fts_score: float | None = None
    exact_score: float | None = None
    hybrid_score: float | None = None
    rerank_score: float | None = None


class Citation(BaseModel):
    """Citation attached to an assistant answer (spec 12 §2)."""

    citation_id: str
    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    status: str
    effective_date: date
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    locator_type: str | None = None
    locator_label: str | None = None
    section_path: list[str] = Field(default_factory=list)
    section_number: str | None = None
    sign_code: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    source_url: str | None = None
    text_snippet: str
    verification_status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    """Final agent output persisted to qa_messages."""

    content: str
    citations: list[Citation] = Field(default_factory=list)
    scope: ScopeLabel
    disclaimer_shown: bool
    is_out_of_scope: bool = False
    latency_ms: int | None = Field(default=None, ge=0)
