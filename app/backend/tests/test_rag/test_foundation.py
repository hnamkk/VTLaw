"""Foundation tests: ORM model structure + RAG Pydantic schemas.

No database required — these assert the schema contracts and table definitions
so CI stays green before the DB-backed integration tests land.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.models import ChatMessage, ChatSession, DocumentChunk, LegalDocument
from src.schemas.rag import (
    AgentResponse,
    Citation,
    RetrievedChunk,
    ScopeLabel,
    ScopeResult,
    VerificationStatus,
)


# --------------------------------------------------------------------------- #
# ORM model structure
# --------------------------------------------------------------------------- #
def test_table_names():
    assert LegalDocument.__tablename__ == "legal_documents"
    assert DocumentChunk.__tablename__ == "document_chunks"


def test_embedding_dim_matches_settings():
    col = DocumentChunk.__table__.c.embedding_vector
    assert col.type.dim == settings.EMBEDDING_DIM == 1536


def test_point_num_width_allows_complex_numbering():
    # Vietnamese legal points can exceed single chars (e.g. "đ", nested ids).
    assert DocumentChunk.__table__.c.point_num.type.length == 10


def test_replaced_by_id_is_indexed():
    # validity_checker looks up replacements by replaced_by_id; must be indexed.
    indexes = {idx.name for idx in LegalDocument.__table__.indexes}
    assert "idx_legal_docs_replaced_by" in indexes


def test_chat_messages_enforce_session_owner_fk():
    constraints = {constraint.name for constraint in ChatMessage.__table__.constraints}
    session_constraints = {constraint.name for constraint in ChatSession.__table__.constraints}

    assert "uq_qa_sessions_session_user" in session_constraints
    assert "fk_qa_messages_session_user" in constraints


def test_source_checksum_has_unique_partial_index():
    index = next(
        idx
        for idx in LegalDocument.__table__.indexes
        if idx.name == "uq_legal_docs_source_checksum"
    )

    assert index.unique is True
    assert "source_checksum IS NOT NULL" in str(index.dialect_options["postgresql"]["where"])


def test_chunk_has_denormalized_status_and_date():
    cols = DocumentChunk.__table__.c
    assert "status" in cols
    assert "effective_date" in cols


def test_text_tsv_is_readonly_generated_column():
    # text_tsv must be a generated (Computed) column so it is never written by the app.
    col = DocumentChunk.__table__.c.text_tsv
    assert col.computed is not None
    assert col.computed.persisted is True


# --------------------------------------------------------------------------- #
# Pydantic schemas
# --------------------------------------------------------------------------- #
def test_scope_result_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        ScopeResult(label=ScopeLabel.in_scope, score=1.5)


def test_citation_roundtrip():
    c = Citation(
        citation_id="c1",
        chunk_id="ch1",
        doc_id="d1",
        doc_title="NĐ 336/2025/NĐ-CP",
        doc_type="NGHI_DINH",
        status="active",
        effective_date=date(2026, 3, 1),
        article_num=9,
        clause_num=1,
        point_num="a",
        text_snippet="Phạt tiền từ 400.000 đến 600.000 đồng",
        verification_status=VerificationStatus.verified,
        confidence=0.93,
    )
    assert c.verification_status == VerificationStatus.verified
    assert c.confidence == 0.93


def test_citation_confidence_bounds():
    with pytest.raises(ValidationError):
        Citation(
            citation_id="c1",
            chunk_id="ch1",
            doc_id="d1",
            doc_title="t",
            doc_type="NGHI_DINH",
            status="active",
            effective_date=date(2026, 3, 1),
            text_snippet="x",
            verification_status=VerificationStatus.verified,
            confidence=1.2,
        )


def test_retrieved_chunk_optional_scores_default_none():
    rc = RetrievedChunk(
        chunk_id="ch1",
        doc_id="d1",
        doc_title="t",
        chunk_type="khoan",
        status="active",
        effective_date=date(2026, 3, 1),
        text_snippet="x",
    )
    assert rc.vector_score is None
    assert rc.rerank_score is None


def test_agent_response_defaults():
    r = AgentResponse(
        content="...",
        scope=ScopeLabel.in_scope,
        disclaimer_shown=True,
    )
    assert r.citations == []
    assert r.is_out_of_scope is False
