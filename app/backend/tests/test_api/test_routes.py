import json
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.v1.chat import _create_or_get_owned_session, _persist_assistant_message_if_owned
from src.auth.dependencies import require_user
from src.core.rate_limit import SlidingWindowRateLimiter
from src.db.session import get_session
from src.main import app
from src.rag.prompts import LEGAL_DISCLAIMER
from src.schemas.rag import Citation, VerificationStatus


class _ListResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def all(self):
        return self.rows


class _ListDocumentsSession:
    def __init__(self):
        self.calls = 0

    async def execute(self, _statement):
        self.calls += 1
        if self.calls == 1:
            return _ListResult(scalar_value=0)
        return _ListResult(rows=[])


class _ScalarOneResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _ScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)


class _DeleteResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _ChatSessionApiSession:
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []
        self.statements = []
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, value):
        self.refreshed.append(value)
        now = datetime(2026, 6, 28, 10, 5, tzinfo=timezone.utc)
        if not isinstance(getattr(value, "updated_at", None), datetime):
            value.updated_at = now
        if not isinstance(getattr(value, "bookmarked_at", None), datetime):
            value.bookmarked_at = now


def _chat_user(user_id="10010010-0100-1001-0010-010010010055"):
    return SimpleNamespace(user_id=user_id, role="USER", is_active=True)


def _chat_session(
    *,
    session_id="20020020-0200-2002-0020-020020020055",
    user_id="10010010-0100-1001-0010-010010010055",
    title="Vượt đèn đỏ",
):
    now = datetime(2026, 6, 28, tzinfo=timezone.utc)
    return SimpleNamespace(
        session_id=session_id,
        user_id=user_id,
        title=title,
        is_bookmarked=False,
        bookmark_title=None,
        bookmarked_at=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_stream_empty_question(client):
    """POST /api/v1/chat/stream with empty question should be rejected by Pydantic."""
    response = await client.post("/api/v1/chat/stream", json={"question": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_public_documents_endpoint_returns_active_documents(client):
    session = _ListDocumentsSession()

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/documents?page=1&page_size=20")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["page_size"] == 20
    assert isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_chat_stream_missing_question(client):
    """POST /api/v1/chat/stream without question field should be rejected."""
    response = await client.post("/api/v1/chat/stream", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_sessions_require_authentication(client):
    response = await client.get("/api/v1/chat/sessions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_sessions_list_returns_owned_sessions(client):
    session = _ChatSessionApiSession(results=[_ScalarsResult([_chat_session()])])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.get("/api/v1/chat/sessions")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["title"] == "Vượt đèn đỏ"
    assert payload["items"][0]["session_id"] == "20020020-0200-2002-0020-020020020055"
    assert payload["items"][0]["is_bookmarked"] is False


@pytest.mark.asyncio
async def test_bookmarked_chat_sessions_require_authentication(client):
    response = await client.get("/api/v1/chat/bookmarks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_notifications_require_authentication(client):
    response = await client.get("/api/v1/notifications")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_repeal_queue_endpoint_is_not_exposed(client):
    response = await client.post(
        f"/api/v1/admin/documents/{uuid.uuid4()}/repeal",
        json={
            "expiry_date": "2026-07-01",
            "reason": "Văn bản đã được thay thế.",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_mark_notification_read_returns_404_for_missing_notification(client):
    class MissingNotificationSession:
        async def scalar(self, _statement):
            return None

    async def override_session():
        yield MissingNotificationSession()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.patch(f"/api/v1/notifications/{uuid.uuid4()}/read")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter()

    assert (await limiter.check("public-chat:test", limit=2, window_seconds=60)).allowed is True
    assert (await limiter.check("public-chat:test", limit=2, window_seconds=60)).allowed is True
    denied = await limiter.check("public-chat:test", limit=2, window_seconds=60)

    assert denied.allowed is False
    assert denied.retry_after_seconds > 0
    assert denied.limit == 2
    assert denied.window_seconds == 60


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter_checks_many_without_counting_denied_hits():
    limiter = SlidingWindowRateLimiter()

    assert (await limiter.check_many([("burst", 5, 60), ("sustained", 1, 600)])).allowed is True
    denied = await limiter.check_many([("burst", 5, 60), ("sustained", 1, 600)])
    assert denied.allowed is False
    assert denied.limit == 1

    assert (await limiter.check("burst", limit=5, window_seconds=60)).allowed is True
    assert (await limiter.check("burst", limit=5, window_seconds=60)).allowed is True
    assert (await limiter.check("burst", limit=5, window_seconds=60)).allowed is True
    assert (await limiter.check("burst", limit=5, window_seconds=60)).allowed is True
    assert (await limiter.check("burst", limit=5, window_seconds=60)).allowed is False


@pytest.mark.asyncio
async def test_bookmarked_chat_sessions_returns_owned_saved_sessions(client):
    saved = _chat_session(title="Mức phạt quá tải")
    saved.is_bookmarked = True
    saved.bookmark_title = "Xe tải quá tải"
    saved.bookmarked_at = datetime(2026, 6, 28, 10, tzinfo=timezone.utc)
    session = _ChatSessionApiSession(results=[_ScalarsResult([saved])])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.get("/api/v1/chat/bookmarks")
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["bookmark_title"] == "Xe tải quá tải"
    assert payload["items"][0]["is_bookmarked"] is True


@pytest.mark.asyncio
async def test_bookmark_chat_session_updates_owned_session(client):
    owned = _chat_session()
    session = _ChatSessionApiSession(results=[_ScalarOneResult(owned)])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.patch(
            f"/api/v1/chat/sessions/{owned.session_id}/bookmark",
            json={"bookmark_title": "  Mức phạt quá tải   xe tải  "},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["bookmark_title"] == "Mức phạt quá tải xe tải"
    assert payload["session"]["is_bookmarked"] is True
    assert owned.is_bookmarked is True
    assert session.commits == 1
    assert session.refreshed == [owned]


@pytest.mark.asyncio
async def test_bookmark_chat_session_returns_404_when_not_owned(client):
    session = _ChatSessionApiSession(results=[_ScalarOneResult(None)])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.patch(
            "/api/v1/chat/sessions/30030030-0300-3003-0030-030030030055/bookmark",
            json={"bookmark_title": "Mức phạt quá tải"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 404
    assert session.commits == 0


@pytest.mark.asyncio
async def test_delete_chat_session_returns_404_when_not_owned(client):
    session = _ChatSessionApiSession(results=[_DeleteResult(rowcount=0)])

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.delete(
            "/api/v1/chat/sessions/30030030-0300-3003-0030-030030030055"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 404
    assert session.commits == 0


@pytest.mark.asyncio
async def test_chat_session_path_rejects_invalid_uuid(client):
    app.dependency_overrides[require_user] = lambda: _chat_user()
    try:
        response = await client.get("/api/v1/chat/sessions/not-a-uuid/messages")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_or_get_owned_session_uses_atomic_insert():
    owned = _chat_session()
    session = _ChatSessionApiSession(results=[SimpleNamespace(), _ScalarOneResult(owned)])

    result = await _create_or_get_owned_session(
        session,
        session_id=owned.session_id,
        user_id=owned.user_id,
        question="Mức phạt vượt đèn đỏ?",
    )

    assert result is owned
    assert "ON CONFLICT" in str(session.statements[0])


@pytest.mark.asyncio
async def test_create_or_get_owned_session_rejects_existing_other_owner():
    session = _ChatSessionApiSession(results=[SimpleNamespace(), _ScalarOneResult(None)])

    with pytest.raises(HTTPException) as exc_info:
        await _create_or_get_owned_session(
            session,
            session_id="20020020-0200-2002-0020-020020020055",
            user_id="10010010-0100-1001-0010-010010010055",
            question="Mức phạt vượt đèn đỏ?",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_deleted_session_is_not_recreated_when_stream_finishes():
    session = _ChatSessionApiSession(results=[_ScalarOneResult(None)])

    persisted = await _persist_assistant_message_if_owned(
        session,
        session_id="20020020-0200-2002-0020-020020020055",
        user_id="10010010-0100-1001-0010-010010010055",
        done_payload={
            "content": "Câu trả lời",
            "citations": [],
            "faithfulness_score": None,
            "is_out_of_scope": False,
        },
    )

    assert persisted is False
    assert session.added == []
    assert session.commits == 0


@pytest.mark.asyncio
async def test_chat_stream_done_contains_guarded_content_and_complete_citation(client, monkeypatch):
    citation = Citation(
        citation_id="citation-1",
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_title="Nghị định kiểm thử",
        doc_type="NGHI_DINH",
        status="active",
        effective_date=date(2026, 1, 1),
        article_num=9,
        clause_num=1,
        locator_type="article",
        locator_label="Dieu 9 Khoan 1",
        section_path=["Chuong II", "Dieu 9"],
        section_number="9",
        asset_ids=["asset-1"],
        source_url="https://example.test/source",
        text_snippet="Nội dung kiểm thử.",
        verification_status=VerificationStatus.verified,
        confidence=0.95,
    )
    final_response = f"Theo Điều 9, Khoản 1.\n\n{LEGAL_DISCLAIMER}"

    class FakeAgent:
        def __init__(self):
            self.config = None

        async def ainvoke(self, *_args, **_kwargs):
            self.config = _kwargs["config"]
            return {
                "final_response": final_response,
                "verified_citations": [citation],
                "faithfulness_score": 0.95,
                "is_out_of_scope": False,
                "reranker_failed": True,
                "reranker_used": False,
                "reranker_error_code": "AUTHZ_INSUFFICIENT_BALANCE",
                "low_confidence": False,
                "retrieval_candidate_count": 6,
                "rerank_top_score": 0.88,
                "guardrail_triggered": False,
                "guardrail_stage": None,
                "guardrail_reason": None,
                "response_document_sources": [
                    {
                        "document_id": "doc-1",
                        "title": "Nghi dinh kiem thu",
                        "issuing_body": "Chinh phu",
                        "date": date(2026, 1, 1),
                        "url": "https://example.test/source",
                    }
                ],
                "response_historical_references": [],
            }

    fake_agent = FakeAgent()
    monkeypatch.setattr("src.api.v1.chat._rag_agent", fake_agent)
    monkeypatch.setattr("src.api.v1.chat.ChatOpenAI", lambda **_kwargs: object())

    response = await client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": "20020020-0200-2002-0020-020020020055",
            "question": "Mức phạt là bao nhiêu?",
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert all(event["type"] != "token" for event in events)
    assert done["content"] == final_response
    assert LEGAL_DISCLAIMER in done["content"]
    assert done["citations"][0]["chunk_id"] == "chunk-1"
    assert done["citations"][0]["status"] == "active"
    assert done["citations"][0]["effective_date"] == "2026-01-01"
    assert done["citations"][0]["locator_type"] == "article"
    assert done["citations"][0]["locator_label"] == "Dieu 9 Khoan 1"
    assert done["citations"][0]["section_path"] == ["Chuong II", "Dieu 9"]
    assert done["citations"][0]["section_number"] == "9"
    assert done["citations"][0]["asset_ids"] == ["asset-1"]
    assert done["citations"][0]["source_url"] == "https://example.test/source"
    assert done["document_sources"] == [
        {
            "document_id": "doc-1",
            "title": "Nghi dinh kiem thu",
            "issuing_body": "Chinh phu",
            "date": "2026-01-01",
            "url": "https://example.test/source",
        }
    ]
    assert done["reranker_failed"] is True
    assert done["reranker_error_code"] == "AUTHZ_INSUFFICIENT_BALANCE"
    assert done["guardrail_triggered"] is False
    assert done["guardrail_stage"] is None
    assert done["guardrail_reason"] is None
    assert fake_agent.config["configurable"]["thread_id"] == f"chat:{done['trace_id']}"
    assert fake_agent.config["configurable"]["thread_id"] != done["session_id"]


@pytest.mark.asyncio
async def test_chat_stream_clarification_done_event_exposes_structured_metadata(
    client, monkeypatch
):
    clarification_text = (
        "Xin lỗi, tôi chưa hiểu rõ bạn đang muốn hỏi nội dung nào.\n\n"
        "Bạn vui lòng nêu rõ hành vi, loại xe hoặc văn bản bạn muốn tra cứu."
    )
    final_response = f"{clarification_text}\n\n{LEGAL_DISCLAIMER}"

    class FakeAgent:
        async def ainvoke(self, *_args, **_kwargs):
            return {
                "final_response": final_response,
                "verified_citations": [],
                "faithfulness_score": None,
                "is_out_of_scope": False,
                "reranker_failed": False,
                "reranker_used": False,
                "reranker_error_code": None,
                "low_confidence": False,
                "retrieval_candidate_count": 0,
                "rerank_top_score": None,
                "guardrail_triggered": True,
                "guardrail_stage": "input",
                "guardrail_reason": "query_clarification",
                "response_document_sources": [],
                "response_historical_references": [],
            }

    monkeypatch.setattr("src.api.v1.chat._rag_agent", FakeAgent())
    monkeypatch.setattr("src.api.v1.chat.ChatOpenAI", lambda **_kwargs: object())

    response = await client.post(
        "/api/v1/chat/stream",
        json={
            "session_id": "20020020-0200-2002-0020-020020020055",
            "question": "Thế còn trường hợp này thì sao?",
        },
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert done["content"] == final_response
    assert done["answer_mode"] == "clarification_needed"
    assert done["clarification_question"] == clarification_text
    assert done["citations"] == []
    assert done["provision_citations"] == []
    assert done["guardrail_triggered"] is True
    assert done["guardrail_stage"] == "input"
    assert done["guardrail_reason"] == "query_clarification"


@pytest.mark.asyncio
async def test_chat_stream_rejects_invalid_session_uuid(client):
    response = await client.post(
        "/api/v1/chat/stream",
        json={"session_id": "not-a-uuid", "question": "Mức phạt là bao nhiêu?"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_stream_rejects_invalid_bearer_token(client):
    response = await client.post(
        "/api/v1/chat/stream",
        headers={"Authorization": "Bearer not-a-valid-token"},
        json={"question": "Mức phạt là bao nhiêu?"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoint_requires_authentication(client):
    response = await client.get("/api/v1/admin/legal-kb/revisions?page=1&page_size=1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_chat_endpoint_is_not_exposed(client):
    response = await client.post("/chat", json={"message": "hello"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legacy_admin_queue_endpoint_is_not_exposed(client):
    response = await client.get("/api/v1/admin/queue")
    assert response.status_code == 404
