from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.api.v1.chat import _message_out, _recent_conversation_context
from src.models.chat_session import ChatMessage


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return _RowsResult(self.rows)


@pytest.mark.asyncio
async def test_recent_conversation_context_strips_disclaimer_and_keeps_roles():
    session = _FakeSession(
        [
            ("user", "Khong doi mu bao hiem"),
            (
                "assistant",
                "Theo quy dinh hien hanh.\n\nLƯU Ý PHÁP LÝ:\nThong tin chi mang tinh tham khao.",
            ),
        ]
    )

    context = await _recent_conversation_context(
        session,
        session_id="session-1",
        user_id="user-1",
    )

    assert "Người dùng: Khong doi mu bao hiem" in context
    assert "Trợ lý: Theo quy dinh hien hanh." in context
    assert "LƯU Ý PHÁP LÝ" not in context


@pytest.mark.asyncio
async def test_recent_conversation_context_returns_empty_string_when_no_rows():
    context = await _recent_conversation_context(
        _FakeSession([]),
        session_id="session-1",
        user_id="user-1",
    )

    assert context == ""


def test_message_out_prefers_persisted_response_metadata():
    message = ChatMessage(
        message_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
        user_id="00000000-0000-0000-0000-000000000003",
        role="assistant",
        content="Thong tin lich su.",
        citations=[],
        response_metadata={
            "risk_level": "medium",
            "answer_mode": "historical",
            "confidence": {"level": "medium", "reason": "historical_or_comparison_request"},
            "provision_citations": [],
            "document_sources": [],
            "historical_references": [
                {
                    "document_id": "doc-old",
                    "title": "Van ban cu",
                    "article_num": 9,
                    "clause_num": 1,
                    "point_num": None,
                    "effective_from": None,
                    "effective_to": None,
                    "status": "expired",
                    "replaced_by": "doc-new",
                }
            ],
            "clarification_question": None,
        },
        is_out_of_scope=False,
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
    )

    out = _message_out(message)

    assert out.answer_mode == "historical"
    assert out.historical_references[0].document_id == "doc-old"
    assert out.provision_citations == []
