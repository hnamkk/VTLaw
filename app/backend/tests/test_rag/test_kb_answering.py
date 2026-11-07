from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from src.rag.agent.nodes import (
    _get_legal_kb_published_document_by_number,
    _legal_kb_document_lookup_response,
    _legal_kb_effective_status_response,
    _legal_kb_standard_summary_response,
    deflect,
    hybrid_retrieve_node,
    inject_disclaimer,
    llm_generate,
    output_guardrail_node,
    parse_query,
    rerank_node,
    scope_classify,
    verify_citation_node,
)
from src.rag.prompts import LEGAL_DISCLAIMER, QUERY_CLARIFICATION_TEMPLATE, SMALL_TALK_TEMPLATE
from src.rag.retrieval import hybrid_legal as hybrid_legal_module
from src.schemas.rag import (
    Citation,
    RetrievedChunk,
    ScopeLabel,
    VerificationStatus,
)


async def _async_result(value):
    return value


class _CaptureScalarSession:
    def __init__(self, value=None):
        self.value = value
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.value

    async def execute(self, statement):
        self.statements.append(statement)

        class _Result:
            def __init__(self, value):
                self._value = value

            def first(self):
                return (self._value, None) if self._value is not None else None

        return _Result(self.value)


def _chunk(
    *,
    chunk_id: str,
    doc_id: str,
    doc_title: str,
    doc_type: str,
    document_number: str,
    rerank_score: float,
    article_num: int,
    clause_num: int | None = None,
    text_snippet: str = "Noi dung can cu.",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_title=doc_title,
        doc_type=doc_type,
        document_number=document_number,
        chunk_type="article",
        article_num=article_num,
        clause_num=clause_num,
        locator_type="article",
        locator_label=f"Dieu {article_num}" + (f" Khoan {clause_num}" if clause_num else ""),
        status="active",
        effective_date=date(2026, 1, 1),
        text_snippet=text_snippet,
        full_text=text_snippet,
        rerank_score=rerank_score,
    )


@pytest.mark.asyncio
async def test_parse_query_clarifies_ambiguous_historical_question():
    result = await parse_query(
        {
            "query": "Truoc day quy dinh nay the nao?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_stage"] == "input"
    assert result["guardrail_reason"] == "query_clarification"


@pytest.mark.asyncio
async def test_parse_query_allows_clear_accented_historical_topic():
    result = await parse_query(
        {
            "query": "Trước đây quy định về đăng ký xe tại nơi cư trú được hiểu như thế nào?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["guardrail_triggered"] is False
    assert result["query_intent"] == "comparison_history"


@pytest.mark.asyncio
async def test_parse_query_allows_relative_historical_lookup_before_current_rule():
    result = await parse_query(
        {
            "query": "Trước khi quy định hiện hành về đăng ký xe có hiệu lực, quy định cũ về nơi đăng ký được nêu ra sao?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["query_intent"] == "comparison_history"
    assert result["guardrail_triggered"] is False
    assert result["guardrail_reason"] is None


@pytest.mark.asyncio
async def test_parse_query_sets_query_intent_for_penalty_question():
    result = await parse_query(
        {
            "query": "Khong doi mu bao hiem bi phat bao nhieu?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["query_intent"] == "penalty"


@pytest.mark.asyncio
async def test_parse_query_clarifies_when_multiple_dates_are_present():
    result = await parse_query(
        {
            "query": "Truoc day vao 2023-01-01 va 2024-01-01 quy dinh the nao?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "temporal_clarification"
    assert "01/01/2023" in result["final_response"]
    assert "01/01/2024" in result["final_response"]
    assert result["query_has_explicit_date"] is True


def test_legal_kb_retrieval_filters_only_current_answerable_units():
    compiled = " ".join(str(condition) for condition in hybrid_legal_module._base_filters(date(2026, 7, 2)))

    assert "legal_kb_legal_documents.legal_status = :legal_status_1" in compiled
    assert "legal_kb_retrieval_units.answerable_status = :answerable_status_1" in compiled
    assert "answerable_status NOT IN" not in compiled


def test_legal_kb_historical_filters_do_not_weaken_active_defaults():
    active_compiled = " ".join(
        str(condition) for condition in hybrid_legal_module._base_filters(date(2026, 7, 2))
    )
    historical_compiled = " ".join(
        str(condition)
        for condition in hybrid_legal_module._base_filters(date(2026, 7, 2), mode="historical")
    )

    assert "legal_kb_legal_documents.legal_status = :legal_status_1" in active_compiled
    assert "legal_kb_legal_documents.legal_status = :legal_status_1" not in historical_compiled
    assert "legal_kb_document_revisions.publication_status IN" in historical_compiled
    assert "legal_kb_retrieval_units.answerable_status IN" in historical_compiled


@pytest.mark.asyncio
async def test_legal_kb_document_lookup_filters_only_active_documents():
    session = _CaptureScalarSession()

    await _get_legal_kb_published_document_by_number(session, "67/2023/ND-CP")

    compiled = str(session.statements[0])
    assert "legal_kb_legal_documents.legal_status = :legal_status_1" in compiled
    assert "legal_kb_legal_documents.legal_status !=" not in compiled


@pytest.mark.asyncio
async def test_legal_kb_standard_summary_filters_only_active_documents():
    session = _CaptureScalarSession()

    await _legal_kb_standard_summary_response(session, "tom tat 67/2023/ND-CP")

    compiled = str(session.statements[0])
    assert "legal_kb_legal_documents.legal_status = :legal_status_1" in compiled
    assert "legal_kb_legal_documents.legal_status !=" not in compiled


@pytest.mark.asyncio
async def test_parse_query_clarifies_ambiguous_short_question():
    result = await parse_query(
        {
            "query": "Quy dinh nay?",
            "conversation_context": "",
        },
        config={},
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "query_clarification"


@pytest.mark.asyncio
async def test_scope_classify_uses_resolved_follow_up_query(monkeypatch):
    async def fake_classify_scope(query: str):
        raise AssertionError(f"semantic follow-up should not call scope classifier: {query}")

    monkeypatch.setattr("src.rag.agent.nodes.classify_scope", fake_classify_scope)

    command = await scope_classify(
        {
            "query": "Con nop o dau?",
            "normalized_query": "Con nop o dau?",
            "retrieval_query": "Thu tuc dang ky xe can nhung giay to nao? Con nop o dau?",
            "follow_up_used": True,
        }
    )

    assert command.goto == "hybrid_retrieve"
    assert command.update["scope_result"].label == ScopeLabel.in_scope


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_uses_legal_kb_when_flag_enabled(monkeypatch):
    async def fake_embed_query(_query: str) -> list[float]:
        return [0.1, 0.2]

    async def fake_hybrid_retrieve_legal(
        _session,
        query: str,
        _embedding,
        *,
        query_date,
        document_ids=None,
        mode="active",
    ):
        assert query == "Noi dung hien hanh"
        assert query_date == date(2026, 7, 2)
        assert document_ids is None
        assert mode == "active"
        return type("Result", (), {"chunks": []})()

    async def fake_future_notice(*_args, **_kwargs) -> str:
        return "Van ban nay chua co hieu luc."

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(None),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fake_embed_query)
    monkeypatch.setattr("src.rag.agent.nodes.hybrid_retrieve_legal", fake_hybrid_retrieve_legal)
    monkeypatch.setattr(
        "src.rag.agent.nodes.future_effective_notice_for_query",
        fake_future_notice,
    )

    result = await hybrid_retrieve_node(
        {
            "query": "Noi dung hien hanh",
            "normalized_query": "Noi dung hien hanh",
            "retrieval_query": "Noi dung hien hanh",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "future_effective"
    assert result["final_response"] == "Van ban nay chua co hieu luc."


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_legal_kb_standard_summary(monkeypatch):
    class _FakeDocument:
        document_id = "doc-35"
        title = "Luat Duong bo"
        issuing_authority = "Quoc hoi"
        issued_date = date(2024, 6, 27)
        effective_date = date(2025, 1, 1)

    class _FakeSession:
        async def scalar(self, _stmt):
            return "Tom tat chuan cua van ban 35/2024/QH15."

        async def execute(self, _stmt):
            class _Result:
                def first(self):
                    return (_FakeDocument(), "https://example.test/35")

            return _Result()

    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("summary request should not call embedding")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-35",)),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "tóm tắt văn bản 35/2024/QH15",
            "normalized_query": "tóm tắt văn bản 35/2024/QH15",
            "retrieval_query": "tóm tắt văn bản 35/2024/QH15",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": _FakeSession()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "legal_kb_standard_summary"
    assert result["final_response"] == "Tom tat chuan cua van ban 35/2024/QH15."
    assert result["response_document_sources"] == [
        {
            "document_id": "doc-35",
            "title": "Luat Duong bo",
            "issuing_body": "Quoc hoi",
            "date": date(2024, 6, 27),
            "url": "https://example.test/35",
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_does_not_fallback_when_standard_summary_missing(monkeypatch):
    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("summary request without approved summary should not run retrieval")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-67",)),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._legal_kb_standard_summary_response",
        lambda *_args, **_kwargs: _async_result(None),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "tom tat van ban 67/2023/ND-CP",
            "normalized_query": "tom tat van ban 67/2023/ND-CP",
            "retrieval_query": "tom tat van ban 67/2023/ND-CP",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "legal_kb_standard_summary"
    assert (
        result["final_response"]
        == "Xin lỗi, tôi chưa có bản tóm tắt chuẩn đã duyệt cho văn bản số hiệu 67/2023/ND-CP."
    )


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_simple_message_for_unknown_document_number(monkeypatch):
    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("unknown explicit document number should not run retrieval")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(()),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "noi dung van ban 999/2026/QH99",
            "normalized_query": "noi dung van ban 999/2026/QH99",
            "retrieval_query": "noi dung van ban 999/2026/QH99",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "legal_kb_document_not_found"
    assert (
        result["final_response"]
        == "Xin lỗi, tôi chưa tìm thấy văn bản số hiệu 999/2026/QH99 đang được công bố trong kho dữ liệu hiện tại."
    )


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_document_lookup_without_embedding(monkeypatch):
    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("document lookup should not run embedding")

    class _FakeDocument:
        document_id = "doc-36"
        title = "Van ban 36"
        issuing_authority = "Quoc hoi"
        issued_date = date(2024, 6, 27)
        effective_date = date(2025, 1, 1)

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-36",)),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._legal_kb_document_lookup_response",
        lambda *_args, **_kwargs: _async_result("Van ban 36/2024/QH15 co tieu de ..."),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._get_legal_kb_published_document_bundle_by_number",
        lambda *_args, **_kwargs: _async_result(
            SimpleNamespace(document=_FakeDocument(), source_url="https://example.test/36")
        ),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "noi dung van ban 36/2024/QH15",
            "normalized_query": "noi dung van ban 36/2024/QH15",
            "retrieval_query": "noi dung van ban 36/2024/QH15",
            "query_intent": "document_lookup",
            "query_document_number": "36/2024/QH15",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "legal_kb_document_lookup"
    assert result["final_response"] == "Van ban 36/2024/QH15 co tieu de ..."
    assert result["response_document_sources"] == [
        {
            "document_id": "doc-36",
            "title": "Van ban 36",
            "issuing_body": "Quoc hoi",
            "date": date(2024, 6, 27),
            "url": "https://example.test/36",
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_effective_status_without_embedding(monkeypatch):
    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("effective status lookup should not run embedding")

    class _FakeDocument:
        document_id = "doc-36"
        title = "Van ban 36"
        issuing_authority = "Quoc hoi"
        issued_date = date(2024, 6, 27)
        effective_date = date(2025, 1, 1)

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-36",)),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._legal_kb_effective_status_response",
        lambda *_args, **_kwargs: _async_result("Van ban 36/2024/QH15 hien dang co hieu luc."),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._get_legal_kb_published_document_bundle_by_number",
        lambda *_args, **_kwargs: _async_result(
            SimpleNamespace(document=_FakeDocument(), source_url="https://example.test/36")
        ),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "van ban 36/2024/QH15 con hieu luc khong",
            "normalized_query": "van ban 36/2024/QH15 con hieu luc khong",
            "retrieval_query": "van ban 36/2024/QH15 con hieu luc khong",
            "query_intent": "effective_status",
            "query_document_number": "36/2024/QH15",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["retrieved_contexts"] == []
    assert result["guardrail_reason"] == "legal_kb_effective_status"
    assert result["final_response"] == "Van ban 36/2024/QH15 hien dang co hieu luc."
    assert result["response_document_sources"] == [
        {
            "document_id": "doc-36",
            "title": "Van ban 36",
            "issuing_body": "Quoc hoi",
            "date": date(2024, 6, 27),
            "url": "https://example.test/36",
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_summary_uses_current_query_when_history_has_other_doc(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_standard_summary(_session, query: str) -> str:
        captured["query"] = query
        return "Tom tat chuan cua van ban 36/2024/QH15."

    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("summary request should not call embedding")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-36",)),
    )
    monkeypatch.setattr("src.rag.agent.nodes._legal_kb_standard_summary_response", fake_standard_summary)
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "tom tat van ban 36/2024/QH15",
            "normalized_query": "tom tat van ban 36/2024/QH15",
            "retrieval_query": "tom tat van ban 35/2024/QH15 tom tat van ban 36/2024/QH15",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert captured["query"] == "tom tat van ban 36/2024/QH15"
    assert result["final_response"] == "Tom tat chuan cua van ban 36/2024/QH15."


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_legal_kb_retrieval_uses_current_explicit_document(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_embed_query(_query: str) -> list[float]:
        return [0.1]

    async def fake_hybrid_retrieve_legal(
        _session,
        query: str,
        _embedding,
        *,
        query_date,
        document_ids=None,
        mode="active",
    ):
        captured["query"] = query
        assert query_date == date(2026, 7, 2)
        assert document_ids == ("doc-36",)
        assert mode == "active"
        return SimpleNamespace(chunks=[])

    async def fake_future_notice(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-36",)),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fake_embed_query)
    monkeypatch.setattr("src.rag.agent.nodes.hybrid_retrieve_legal", fake_hybrid_retrieve_legal)
    monkeypatch.setattr("src.rag.agent.nodes.future_effective_notice_for_query", fake_future_notice)

    result = await hybrid_retrieve_node(
        {
            "query": "noi dung van ban 36/2024/QH15",
            "normalized_query": "noi dung van ban 36/2024/QH15",
            "retrieval_query": "noi dung van ban 35/2024/QH15 noi dung van ban 36/2024/QH15",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert captured["query"] == "noi dung van ban 36/2024/QH15"
    assert result["retrieved_contexts"] == []


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_lifecycle_metadata_for_expired_document(monkeypatch):
    class _FakeDocument:
        document_id = "doc-expired"
        document_number = "12/2020/ND-CP"
        title = "Van ban da het hieu luc"
        issuing_authority = "Chinh phu"
        issued_date = date(2020, 1, 2)
        effective_date = date(2020, 3, 1)
        expiry_date = date(2024, 7, 1)
        legal_status = "expired"

    class _FakeReplacementDocument:
        document_id = "doc-new"
        document_number = "44/2024/ND-CP"
        title = "Van ban thay the"

    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("effective status lifecycle path should not run embedding")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-expired",)),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._legal_kb_effective_status_response",
        lambda *_args, **_kwargs: _async_result(None),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._get_legal_kb_lifecycle_document_bundle_by_number",
        lambda *_args, **_kwargs: _async_result(
            SimpleNamespace(document=_FakeDocument(), source_url="https://example.test/expired")
        ),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._find_replacement_bundle_for_document",
        lambda *_args, **_kwargs: _async_result(
            SimpleNamespace(
                document=_FakeReplacementDocument(),
                source_url="https://example.test/replacement",
            )
        ),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "van ban 12/2020/ND-CP het hieu luc chua",
            "normalized_query": "van ban 12/2020/ND-CP het hieu luc chua",
            "retrieval_query": "van ban 12/2020/ND-CP het hieu luc chua",
            "query_intent": "effective_status",
            "query_document_number": "12/2020/ND-CP",
            "query_date": date(2026, 7, 2),
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["guardrail_reason"] == "legal_kb_effective_status"
    assert result["status_filter"] == "historical"
    assert "01/07/2024" in result["final_response"]
    assert "44/2024/ND-CP - Van ban thay the" in result["final_response"]
    assert result["response_document_sources"] == [
        {
            "document_id": "doc-expired",
            "title": "Van ban da het hieu luc",
            "issuing_body": "Chinh phu",
            "date": date(2020, 1, 2),
            "url": "https://example.test/expired",
        }
    ]
    assert result["response_historical_references"] == [
        {
            "document_id": "doc-expired",
            "title": "Van ban da het hieu luc",
            "article_num": None,
            "clause_num": None,
            "point_num": None,
            "effective_from": date(2020, 3, 1),
            "effective_to": date(2024, 7, 1),
            "status": "expired",
            "replaced_by": "44/2024/ND-CP - Van ban thay the",
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_returns_historical_direct_response(monkeypatch):
    captured: dict[str, object] = {}
    chunk = RetrievedChunk(
        chunk_id="unit-h1",
        doc_id="doc-h1",
        doc_title="Nghi dinh cu",
        doc_type="NGHI_DINH",
        document_number="10/2019/ND-CP",
        chunk_type="article",
        article_num=4,
        clause_num=2,
        locator_type="article",
        locator_label="Dieu 4 Khoan 2",
        status="historical",
        effective_date=date(2019, 6, 1),
        expiry_date=date(2023, 12, 31),
        text_snippet="Nguoi lai xe phai thuc hien quy dinh lich su.",
        full_text="Nguoi lai xe phai thuc hien quy dinh lich su.",
    )

    async def fake_embed_query(_query: str) -> list[float]:
        return [0.3]

    async def fake_hybrid_retrieve_legal(
        _session,
        query: str,
        _embedding,
        *,
        query_date,
        document_ids=None,
        mode="active",
    ):
        captured["query"] = query
        captured["query_date"] = query_date
        captured["document_ids"] = document_ids
        captured["mode"] = mode
        return SimpleNamespace(chunks=[chunk])

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-h1",)),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fake_embed_query)
    monkeypatch.setattr("src.rag.agent.nodes.hybrid_retrieve_legal", fake_hybrid_retrieve_legal)

    result = await hybrid_retrieve_node(
        {
            "query": "Van ban 10/2019/ND-CP truoc day quy dinh the nao?",
            "normalized_query": "Van ban 10/2019/ND-CP truoc day quy dinh the nao?",
            "retrieval_query": "Van ban 10/2019/ND-CP truoc day quy dinh the nao?",
            "query_intent": "comparison_history",
            "query_document_number": "10/2019/ND-CP",
            "query_date": date(2021, 6, 1),
            "query_has_explicit_date": True,
        },
        config={"configurable": {"db_session": object()}},
    )

    assert captured["mode"] == "historical"
    assert captured["query_date"] == date(2021, 6, 1)
    assert result["guardrail_reason"] == "legal_kb_historical_lookup"
    assert result["status_filter"] == "historical"
    assert "không phải căn cứ pháp lý hiện hành" in result["final_response"]
    assert result["response_historical_references"] == [
        {
            "document_id": "doc-h1",
            "title": "Nghi dinh cu",
            "article_num": 4,
            "clause_num": 2,
            "point_num": None,
            "effective_from": date(2019, 6, 1),
            "effective_to": date(2023, 12, 31),
            "status": "historical",
            "replaced_by": None,
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retrieve_node_clarifies_when_historical_document_has_multiple_periods(
    monkeypatch,
):
    async def fail_embed_query(_query: str) -> list[float]:
        raise AssertionError("multiple historical periods should clarify before retrieval")

    monkeypatch.setattr(
        "src.rag.agent.nodes._document_ids_for_explicit_refs",
        lambda *_args, **_kwargs: _async_result(("doc-h1",)),
    )
    monkeypatch.setattr(
        "src.rag.agent.nodes._historical_periods_for_documents",
        lambda *_args, **_kwargs: _async_result(
            [
                (date(2019, 1, 1), date(2021, 1, 1)),
                (date(2021, 1, 1), date(2024, 1, 1)),
            ]
        ),
    )
    monkeypatch.setattr("src.rag.agent.nodes.embed_query", fail_embed_query)

    result = await hybrid_retrieve_node(
        {
            "query": "Truoc day van ban 10/2019/ND-CP quy dinh the nao?",
            "normalized_query": "Truoc day van ban 10/2019/ND-CP quy dinh the nao?",
            "retrieval_query": "Truoc day van ban 10/2019/ND-CP quy dinh the nao?",
            "query_intent": "comparison_history",
            "query_document_number": "10/2019/ND-CP",
            "query_date": date(2026, 7, 2),
            "query_has_explicit_date": False,
        },
        config={"configurable": {"db_session": object()}},
    )

    assert result["guardrail_reason"] == "temporal_clarification"
    assert result["status_filter"] == "historical"
    assert "01/01/2019" in result["final_response"]
    assert "31/12/2020" in result["final_response"]


def test_legal_kb_extract_document_refs_supports_common_legal_numbers():
    refs = hybrid_legal_module._extract_document_refs(
        "Hoi 36/2024/QH15 va 67/2023/ND-CP, them 67/2023/N\u0110-CP."
    )

    assert refs == ("36/2024/QH15", "67/2023/ND-CP", "67/2023/N\u0110-CP")


def test_legal_kb_raw_lookup_terms_normalizes_vietnamese_consistently():
    terms = hybrid_legal_module._raw_lookup_terms("\u0110\u01b0\u1eddng cao t\u1ed1c l\u00e0 g\u00ec? M\u0169 b\u1ea3o hi\u1ec3m!")

    assert "duong" in terms
    assert "cao" in terms
    assert "toc" in terms
    assert "mu" in terms
    assert "bao" in terms
    assert "hiem" in terms
    assert "l\u00e0" not in terms


def test_legal_kb_exact_match_score_prefers_term_coverage_over_single_term_hits():
    from types import SimpleNamespace

    relevant = SimpleNamespace(
        text="Ng\u01b0\u1eddi l\u00e1i xe m\u00f4 t\u00f4 ph\u1ea3i \u0111\u1ed9i m\u0169 b\u1ea3o hi\u1ec3m.",
        citation_label="Ch\u01b0\u01a1ng 4 > \u0110i\u1ec1u 26 > Kho\u1ea3n 3",
        doc_title="Lu\u1eadt Tr\u1eadt t\u1ef1, an to\u00e0n giao th\u00f4ng \u0111\u01b0\u1eddng b\u1ed9",
        document_number="36/2024/QH15",
    )
    weak = SimpleNamespace(
        text="R\u00e0o ch\u1eafn \u0111\u1ec3 ng\u0103n kh\u00f4ng cho ng\u01b0\u1eddi tham gia giao th\u00f4ng v\u00e0o khu v\u1ef1c c\u1ea7n b\u1ea3o v\u1ec7.",
        citation_label="Kho\u1ea3n 8",
        doc_title="Lu\u1eadt Tr\u1eadt t\u1ef1, an to\u00e0n giao th\u00f4ng \u0111\u01b0\u1eddng b\u1ed9",
        document_number="36/2024/QH15",
    )
    terms = hybrid_legal_module._raw_lookup_terms(
        "\u0110\u1ed9i m\u0169 b\u1ea3o hi\u1ec3m c\u00f3 b\u1eaft bu\u1ed9c kh\u00f4ng?"
    )

    assert hybrid_legal_module._exact_match_score(relevant, terms, set()) > hybrid_legal_module._exact_match_score(
        weak, terms, set()
    )


def test_legal_kb_exact_match_score_weights_body_over_metadata():
    from types import SimpleNamespace

    body_match = SimpleNamespace(
        text="Noi dung: Ng\u01b0\u1eddi l\u00e1i xe tr\u00ean \u0111\u01b0\u1eddng cao t\u1ed1c ph\u1ea3i tu\u00e2n th\u1ee7 quy t\u1eafc.",
        citation_label="Ch\u01b0\u01a1ng 2 > \u0110i\u1ec1u 22",
        doc_title="Lu\u1eadt Tr\u1eadt t\u1ef1, an to\u00e0n giao th\u00f4ng \u0111\u01b0\u1eddng b\u1ed9",
        document_number="36/2024/QH15",
    )
    metadata_only = SimpleNamespace(
        text="Noi dung: Quy \u0111\u1ecbnh chung kh\u00f4ng n\u00eau c\u1ee5m t\u1eeb c\u1ea7n tra.",
        citation_label="Ch\u01b0\u01a1ng 1",
        doc_title="Lu\u1eadt \u0110\u01b0\u1eddng b\u1ed9",
        document_number="35/2024/QH15",
    )
    terms = hybrid_legal_module._raw_lookup_terms("\u0110\u01b0\u1eddng cao t\u1ed1c l\u00e0 g\u00ec?")

    assert hybrid_legal_module._exact_match_score(body_match, terms, set()) > hybrid_legal_module._exact_match_score(
        metadata_only, terms, set()
    )


@pytest.mark.asyncio
async def test_legal_kb_exact_search_normalizes_both_terms_and_columns():
    captured = {}

    class _Result:
        def all(self):
            return []

    class _Session:
        async def execute(self, stmt):
            captured["stmt"] = stmt
            return _Result()

    await hybrid_legal_module._exact_search(
        _Session(),
        query="\u0110\u01b0\u1eddng cao t\u1ed1c l\u00e0 g\u00ec?",
        query_date=date(2026, 7, 4),
        top_k=5,
        document_ids=None,
    )

    statement = captured["stmt"]
    compiled = str(statement)
    params = statement.compile().params
    assert "citation_label" in compiled
    assert "legal_kb_legal_documents.title" in compiled
    assert "translate" in compiled
    assert "ORDER BY" in compiled
    assert params["term_0"] == "%duong%"
    assert params["term_1"] == "%cao%"
    assert params["term_2"] == "%toc%"


@pytest.mark.asyncio
async def test_legal_kb_explicit_document_number_scopes_all_retrieval_branches(monkeypatch):
    calls: list[tuple[str, tuple[str, ...] | None]] = []

    async def fake_resolve(_session, query: str):
        assert query == "noi dung van ban 36/2024/QH15"
        return ("doc-36",)

    async def fake_branch(name: str, **kwargs):
        calls.append((name, kwargs["document_ids"]))
        return []

    monkeypatch.setattr(hybrid_legal_module, "_document_ids_for_explicit_refs", fake_resolve)
    monkeypatch.setattr(
        hybrid_legal_module,
        "_vector_search",
        lambda *_args, **kwargs: fake_branch("vector", **kwargs),
    )
    monkeypatch.setattr(
        hybrid_legal_module,
        "_fts_search",
        lambda *_args, **kwargs: fake_branch("fts", **kwargs),
    )
    monkeypatch.setattr(
        hybrid_legal_module,
        "_exact_search",
        lambda *_args, **kwargs: fake_branch("exact", **kwargs),
    )

    result = await hybrid_legal_module.hybrid_retrieve_legal(
        session=object(),
        query="noi dung van ban 36/2024/QH15",
        query_embedding=[0.1],
        query_date=date(2026, 7, 2),
    )

    assert result.chunks == []
    assert calls == [
        ("vector", ("doc-36",)),
        ("fts", ("doc-36",)),
        ("exact", ("doc-36",)),
    ]


@pytest.mark.asyncio
async def test_legal_kb_topic_hint_does_not_exclude_other_active_sources(monkeypatch):
    calls: list[tuple[str, tuple[str, ...] | None]] = []
    resolver_queries: list[str] = []

    async def fake_resolve(_session, query: str):
        resolver_queries.append(query)
        if query == "35/2024/QH15":
            return ("doc-35",)
        return None

    async def fake_branch(name: str, **kwargs):
        calls.append((name, kwargs["document_ids"]))
        return []

    monkeypatch.setattr(hybrid_legal_module, "_document_ids_for_explicit_refs", fake_resolve)
    monkeypatch.setattr(
        hybrid_legal_module,
        "_vector_search",
        lambda *_args, **kwargs: fake_branch("vector", **kwargs),
    )
    monkeypatch.setattr(
        hybrid_legal_module,
        "_fts_search",
        lambda *_args, **kwargs: fake_branch("fts", **kwargs),
    )
    monkeypatch.setattr(
        hybrid_legal_module,
        "_exact_search",
        lambda *_args, **kwargs: fake_branch("exact", **kwargs),
    )

    result = await hybrid_legal_module.hybrid_retrieve_legal(
        session=object(),
        query="Luật Đường bộ 2024 tập trung vào hạ tầng và vận tải đường bộ như thế nào?",
        query_embedding=[0.1],
        query_date=date(2026, 7, 2),
    )

    assert result.chunks == []
    assert len(resolver_queries) == 1
    assert calls == [
        ("vector", None),
        ("fts", None),
        ("exact", None),
    ]


@pytest.mark.asyncio
async def test_legal_kb_unknown_explicit_document_number_does_not_search_all_corpus(monkeypatch):
    async def fake_resolve(_session, _query: str):
        return ()

    async def fail_branch(**_kwargs):
        raise AssertionError("unknown explicit document number should not fallback to whole corpus")

    monkeypatch.setattr(hybrid_legal_module, "_document_ids_for_explicit_refs", fake_resolve)
    monkeypatch.setattr(hybrid_legal_module, "_vector_search", lambda *_args, **kwargs: fail_branch(**kwargs))
    monkeypatch.setattr(hybrid_legal_module, "_fts_search", lambda *_args, **kwargs: fail_branch(**kwargs))
    monkeypatch.setattr(hybrid_legal_module, "_exact_search", lambda *_args, **kwargs: fail_branch(**kwargs))

    result = await hybrid_legal_module.hybrid_retrieve_legal(
        session=object(),
        query="noi dung van ban 999/2026/QH99",
        query_embedding=[0.1],
        query_date=date(2026, 7, 2),
    )

    assert result.chunks == []


@pytest.mark.asyncio
async def test_output_guardrail_preserves_future_effective_notice():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "future_effective",
            "guardrail_stage": "retrieval",
            "final_response": "Van ban nay chua co hieu luc.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "future_effective"


@pytest.mark.asyncio
async def test_rerank_node_adds_complementary_role_notice_and_document_sources():
    result = await rerank_node(
        {
            "query": "Khung quy dinh chung ve van tai duong bo gom nhung van ban nao?",
            "normalized_query": "Khung quy dinh chung ve van tai duong bo gom nhung van ban nao?",
            "query_intent": "general_legal",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="law-1",
                    doc_id="doc-law",
                    doc_title="Luat Giao thong duong bo",
                    doc_type="LUAT",
                    document_number="36/2024/QH15",
                    rerank_score=0.82,
                    article_num=1,
                ),
                _chunk(
                    chunk_id="decree-1",
                    doc_id="doc-decree",
                    doc_title="Nghi dinh huong dan",
                    doc_type="NGHI_DINH",
                    document_number="67/2023/ND-CP",
                    rerank_score=0.80,
                    article_num=2,
                ),
                _chunk(
                    chunk_id="circular-1",
                    doc_id="doc-circular",
                    doc_title="Thong tu thuc hien",
                    doc_type="THONG_TU",
                    document_number="12/2025/TT-BGTVT",
                    rerank_score=0.79,
                    article_num=3,
                ),
            ],
        }
    )

    assert "Luat -> Nghi dinh -> Thong tu" in result["evidence_policy_notice"]
    assert result["response_document_sources"] == [
        {
            "document_id": "doc-law",
            "title": "Luat Giao thong duong bo",
            "issuing_body": None,
            "date": date(2026, 1, 1),
            "url": None,
        },
        {
            "document_id": "doc-decree",
            "title": "Nghi dinh huong dan",
            "issuing_body": None,
            "date": date(2026, 1, 1),
            "url": None,
        },
        {
            "document_id": "doc-circular",
            "title": "Thong tu thuc hien",
            "issuing_body": None,
            "date": date(2026, 1, 1),
            "url": None,
        },
    ]


@pytest.mark.asyncio
async def test_llm_generate_includes_complementary_role_notice_in_prompt():
    captured: dict[str, str] = {}

    class _FakeLlm:
        async def ainvoke(self, messages, max_tokens: int):
            captured["prompt"] = messages[-1]["content"]
            return SimpleNamespace(content="Tra loi tong quat.")

    result = await llm_generate(
        {
            "query": "Khung quy dinh chung ve van tai duong bo gom nhung van ban nao?",
            "normalized_query": "Khung quy dinh chung ve van tai duong bo gom nhung van ban nao?",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="law-1",
                    doc_id="doc-law",
                    doc_title="Luat Giao thong duong bo",
                    doc_type="LUAT",
                    document_number="36/2024/QH15",
                    rerank_score=0.82,
                    article_num=1,
                )
            ],
            "low_confidence": False,
            "repealed_notice": None,
            "evidence_policy_notice": (
                "Evidence policy: neu nhieu van ban bo sung nhau, trinh bay theo thu tu "
                "Luat -> Nghi dinh -> Thong tu."
            ),
            "query_date": date(2026, 7, 3),
            "conversation_context": "",
        },
        config={"configurable": {"db_session": None, "llm": _FakeLlm()}},
    )

    assert result["llm_output"] == "Tra loi tong quat."
    assert "Luat -> Nghi dinh -> Thong tu" in captured["prompt"]


@pytest.mark.asyncio
async def test_rerank_node_guides_penalty_questions_to_decree_with_direct_basis():
    result = await rerank_node(
        {
            "query": "Xe may khong doi mu bao hiem bi phat bao nhieu?",
            "normalized_query": "Xe may khong doi mu bao hiem bi phat bao nhieu?",
            "query_intent": "penalty",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="law-1",
                    doc_id="doc-law",
                    doc_title="Luat Giao thong duong bo",
                    doc_type="LUAT",
                    document_number="36/2024/QH15",
                    rerank_score=0.84,
                    article_num=8,
                ),
                _chunk(
                    chunk_id="decree-1",
                    doc_id="doc-decree",
                    doc_title="Nghi dinh xu phat",
                    doc_type="NGHI_DINH",
                    document_number="100/2019/ND-CP",
                    rerank_score=0.82,
                    article_num=7,
                    text_snippet="Phạt tiền đối với người đi xe máy không đội mũ bảo hiểm.",
                ),
            ],
        }
    )

    assert "100/2019/ND-CP" in result["evidence_policy_notice"]
    assert "van ban cap cao hon" in result["evidence_policy_notice"]


@pytest.mark.asyncio
async def test_rerank_node_clarifies_when_short_specific_query_has_divergent_near_tie(
    monkeypatch,
):
    async def fake_rerank_chunks(_query, candidates):
        return SimpleNamespace(
            chunks=candidates,
            reranker_failed=False,
            reranker_used=True,
            error_code=None,
            low_confidence=False,
            top_score=0.81,
        )

    monkeypatch.setattr("src.rag.agent.nodes.rerank_chunks", fake_rerank_chunks)
    monkeypatch.setattr("src.rag.agent.nodes.pack_context", lambda chunks: chunks)

    result = await rerank_node(
        {
            "query": "Bi phat bao nhieu?",
            "normalized_query": "Bi phat bao nhieu?",
            "query_intent": "penalty",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="decree-1",
                    doc_id="doc-decree-1",
                    doc_title="Nghi dinh A",
                    doc_type="NGHI_DINH",
                    document_number="100/2019/ND-CP",
                    rerank_score=0.81,
                    article_num=7,
                    clause_num=2,
                ),
                _chunk(
                    chunk_id="decree-2",
                    doc_id="doc-decree-2",
                    doc_title="Nghi dinh B",
                    doc_type="NGHI_DINH",
                    document_number="123/2021/ND-CP",
                    rerank_score=0.80,
                    article_num=12,
                    clause_num=1,
                ),
            ],
        }
    )

    assert result["guardrail_reason"] == "evidence_clarification"
    assert "chưa đủ tình tiết" in result["final_response"]


@pytest.mark.asyncio
async def test_rerank_node_marks_multiple_possibilities_for_fact_dependent_near_tie(
    monkeypatch,
):
    async def fake_rerank_chunks(_query, candidates):
        return SimpleNamespace(
            chunks=candidates,
            reranker_failed=False,
            reranker_used=True,
            error_code=None,
            low_confidence=False,
            top_score=0.81,
        )

    monkeypatch.setattr("src.rag.agent.nodes.rerank_chunks", fake_rerank_chunks)
    monkeypatch.setattr("src.rag.agent.nodes.pack_context", lambda chunks: chunks)

    result = await rerank_node(
        {
            "query": "Xe khach don khach sai noi quy dinh bi phat bao nhieu khi kinh doanh van tai?",
            "normalized_query": "Xe khach don khach sai noi quy dinh bi phat bao nhieu khi kinh doanh van tai?",
            "query_intent": "penalty",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="decree-1",
                    doc_id="doc-decree-1",
                    doc_title="Nghi dinh A",
                    doc_type="NGHI_DINH",
                    document_number="100/2019/ND-CP",
                    rerank_score=0.81,
                    article_num=7,
                ),
                _chunk(
                    chunk_id="decree-2",
                    doc_id="doc-decree-2",
                    doc_title="Nghi dinh B",
                    doc_type="NGHI_DINH",
                    document_number="123/2021/ND-CP",
                    rerank_score=0.79,
                    article_num=12,
                    text_snippet="Phạt tiền đối với xe khách đón khách sai nơi quy định.",
                ),
            ],
        }
    )

    assert result["guardrail_reason"] == "evidence_multiple_possibilities"
    assert "nhiều trường hợp khác nhau" in result["final_response"]


@pytest.mark.asyncio
async def test_rerank_node_marks_insufficient_for_general_divergent_near_tie(monkeypatch):
    async def fake_rerank_chunks(_query, candidates):
        return SimpleNamespace(
            chunks=candidates,
            reranker_failed=False,
            reranker_used=True,
            error_code=None,
            low_confidence=False,
            top_score=0.78,
        )

    monkeypatch.setattr("src.rag.agent.nodes.rerank_chunks", fake_rerank_chunks)
    monkeypatch.setattr("src.rag.agent.nodes.pack_context", lambda chunks: chunks)

    result = await rerank_node(
        {
            "query": "Quy dinh chung hien nay ve han che xe tai la gi?",
            "normalized_query": "Quy dinh chung hien nay ve han che xe tai la gi?",
            "query_intent": "general_legal",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="decree-1",
                    doc_id="doc-decree-1",
                    doc_title="Nghi dinh A",
                    doc_type="NGHI_DINH",
                    document_number="100/2019/ND-CP",
                    rerank_score=0.78,
                    article_num=7,
                ),
                _chunk(
                    chunk_id="decision-1",
                    doc_id="doc-decision-1",
                    doc_title="Quyet dinh B",
                    doc_type="QUYET_DINH",
                    document_number="22/2024/QD-BGTVT",
                    rerank_score=0.77,
                    article_num=14,
                ),
            ],
        }
    )

    assert result["guardrail_reason"] == "evidence_insufficient"
    assert "chưa thể kết luận một căn cứ duy nhất" in result["final_response"]


@pytest.mark.asyncio
async def test_output_guardrail_preserves_evidence_policy_direct_responses():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "evidence_multiple_possibilities",
            "guardrail_stage": "rerank",
            "final_response": "Toi thay cac can cu gan nhat dang tro toi nhieu truong hop khac nhau.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "evidence_multiple_possibilities"


@pytest.mark.asyncio
async def test_output_guardrail_preserves_legal_kb_standard_summary():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "legal_kb_standard_summary",
            "guardrail_stage": "retrieval",
            "final_response": "Tom tat chuan cua van ban 35/2024/QH15.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "legal_kb_standard_summary"


@pytest.mark.asyncio
async def test_output_guardrail_preserves_legal_kb_document_not_found():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "legal_kb_document_not_found",
            "guardrail_stage": "retrieval",
            "final_response": "Xin lỗi, tôi chưa tìm thấy văn bản số hiệu 999/2026/QH99 đang được công bố trong kho dữ liệu hiện tại.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "legal_kb_document_not_found"


@pytest.mark.asyncio
async def test_output_guardrail_preserves_legal_kb_document_lookup():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "legal_kb_document_lookup",
            "guardrail_stage": "retrieval",
            "final_response": "Van ban 36/2024/QH15 co tieu de ...",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "legal_kb_document_lookup"


@pytest.mark.asyncio
async def test_output_guardrail_preserves_legal_kb_effective_status():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "legal_kb_effective_status",
            "guardrail_stage": "retrieval",
            "final_response": "Van ban 36/2024/QH15 hien dang co hieu luc.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "legal_kb_effective_status"


@pytest.mark.asyncio
async def test_output_guardrail_preserves_legal_kb_historical_lookup():
    result = await output_guardrail_node(
        {
            "guardrail_reason": "legal_kb_historical_lookup",
            "guardrail_stage": "retrieval",
            "final_response": "Thong tin lich su, khong phai can cu hien hanh.",
        }
    )

    assert result["guardrail_triggered"] is True
    assert result["guardrail_reason"] == "legal_kb_historical_lookup"


@pytest.mark.asyncio
async def test_llm_generate_adds_legal_kb_evidence_notice_to_prompt(monkeypatch):
    captured: dict[str, str] = {}

    class _FakeLlm:
        async def ainvoke(self, messages, max_tokens: int):
            captured["prompt"] = messages[-1]["content"]
            captured["max_tokens"] = str(max_tokens)
            return SimpleNamespace(content="Theo Dieu 1, noi dung hien hanh la ...")

    async def fake_assemble_evidence_bundle(*_args, **_kwargs):
        return SimpleNamespace(
            has_conflict=True,
            prompt_notice="Canh bao xung dot: provision `Dieu 1` co nhieu version cung hieu luc.",
        )

    monkeypatch.setattr("src.rag.agent.nodes.assemble_evidence_bundle", fake_assemble_evidence_bundle)

    result = await llm_generate(
        {
            "query": "Noi dung hien hanh Dieu 1?",
            "normalized_query": "Noi dung hien hanh Dieu 1?",
            "retrieved_contexts": [
                RetrievedChunk(
                    chunk_id="unit-1",
                    doc_id="doc-1",
                    doc_title="Thong tu thu nghiem",
                    doc_type="THONG_TU",
                    chunk_type="article",
                    status="active",
                    effective_date=date(2026, 7, 1),
                    text_snippet="Noi dung Dieu 1",
                    full_text="Noi dung Dieu 1",
                )
            ],
            "low_confidence": False,
            "repealed_notice": None,
            "query_date": date(2026, 7, 3),
            "conversation_context": "",
        },
        config={"configurable": {"db_session": object(), "llm": _FakeLlm()}},
    )

    assert result["evidence_notice"].startswith("Canh bao xung dot")
    assert "Canh bao xung dot" in captured["prompt"]
    assert captured["max_tokens"] == "500"


@pytest.mark.asyncio
async def test_legal_kb_document_lookup_response_hides_unpublished_or_suspended_documents():
    class _Session:
        async def scalar(self, _stmt):
            return None

    result = await _legal_kb_document_lookup_response(_Session(), "36/2024/QH15")

    assert result is None


@pytest.mark.asyncio
async def test_legal_kb_effective_status_response_hides_unpublished_or_suspended_documents():
    class _Session:
        async def scalar(self, _stmt):
            return None

    result = await _legal_kb_effective_status_response(_Session(), "36/2024/QH15")

    assert result is None


@pytest.mark.asyncio
async def test_inject_disclaimer_prepends_evidence_notice_before_disclaimer():
    citation = Citation(
        citation_id="citation-1",
        chunk_id="unit-1",
        doc_id="doc-1",
        doc_title="Thong tu thu nghiem",
        doc_type="THONG_TU",
        status="active",
        effective_date=date(2026, 7, 1),
        text_snippet="Noi dung Dieu 1",
        verification_status=VerificationStatus.verified,
        confidence=1.0,
    )

    result = await inject_disclaimer(
        {
            "llm_output": "Theo Dieu 1, noi dung hien hanh la ...",
            "verified_citations": [citation],
            "has_hallucination": False,
            "evidence_notice": "Canh bao xung dot: provision `Dieu 1` co nhieu version cung hieu luc.",
        }
    )

    assert result["final_response"].startswith("Canh bao xung dot")
    assert LEGAL_DISCLAIMER in result["final_response"]


@pytest.mark.asyncio
async def test_deflect_appends_disclaimer_for_direct_guardrail_response():
    result = await deflect({"final_response": QUERY_CLARIFICATION_TEMPLATE})

    assert LEGAL_DISCLAIMER in result["final_response"]
    assert result["disclaimer_appended"] is True


@pytest.mark.asyncio
async def test_deflect_keeps_small_talk_without_legal_disclaimer():
    result = await deflect({"final_response": SMALL_TALK_TEMPLATE})

    assert result["final_response"] == SMALL_TALK_TEMPLATE
    assert result["disclaimer_appended"] is False


@pytest.mark.asyncio
async def test_verify_citation_node_answers_citation_lookup_from_retrieval_units():
    result = await verify_citation_node(
        {
            "query": "Dan can cu ve tem kiem dinh xe co gioi",
            "llm_output": "Chưa tìm thấy căn cứ đủ chắc trong kho dữ liệu.",
            "retrieved_contexts": [
                _chunk(
                    chunk_id="unit-16",
                    doc_id="doc-16",
                    doc_title="Thong tu kiem dinh",
                    doc_type="THONG_TU",
                    document_number="16/2021/TT-BGTVT",
                    rerank_score=0.9,
                    article_num=3,
                    text_snippet="Tem kiem dinh co hieu luc theo thoi han ghi tren tem.",
                )
            ],
        }
    )

    assert result["verified_citations"]
    assert "Thong tu kiem dinh" in result["llm_output"]
    assert "chưa tìm thấy" not in result["llm_output"].lower()
