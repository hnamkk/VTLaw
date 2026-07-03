from __future__ import annotations

from datetime import date, datetime

from src.api.v1.schemas import ChatMessageOut, ChatStreamDoneEvent
from src.rag.response_metadata import build_chat_response_metadata
from src.schemas.rag import Citation, VerificationStatus


def _citation(
    *,
    status: str = "active",
    verification_status: VerificationStatus = VerificationStatus.verified,
) -> Citation:
    return Citation(
        citation_id="citation-1",
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_title="ND 336/2025/ND-CP",
        doc_type="NGHI_DINH",
        status=status,
        effective_date=date(2026, 3, 1),
        article_num=9,
        clause_num=1,
        point_num="a",
        locator_label="Dieu 9 Khoan 1 Diem a",
        text_snippet="Noi dung can cu.",
        verification_status=verification_status,
        confidence=0.95,
    )


def test_chat_stream_done_event_has_stable_defaults():
    payload = ChatStreamDoneEvent(
        type="done",
        trace_id="trace-1",
        session_id="session-1",
        content="Noi dung tra loi.",
    )

    assert payload.answer_mode == "direct"
    assert payload.risk_level == "medium"
    assert payload.confidence.level == "medium"
    assert payload.provision_citations == []
    assert payload.document_sources == []
    assert payload.historical_references == []
    assert payload.citations == []
    assert payload.clarification_question is None


def test_chat_message_out_keeps_legacy_citations_field():
    message = ChatMessageOut(
        message_id="message-1",
        role="assistant",
        content="Noi dung tra loi.",
        citations=[{"citation_id": "legacy-1"}],
        created_at=datetime(2026, 7, 9, 0, 0, 0),
    )

    assert message.citations == [{"citation_id": "legacy-1"}]


def test_build_chat_response_metadata_maps_only_active_supported_citations():
    metadata = build_chat_response_metadata(
        content="Theo Dieu 9 Khoan 1 Diem a, noi dung duoc quy dinh.",
        citations=[
            _citation(),
            _citation(status="repealed"),
            _citation(verification_status=VerificationStatus.unverified),
        ],
        faithfulness_score=0.96,
        is_out_of_scope=False,
    )

    assert metadata["answer_mode"] == "direct"
    assert metadata["risk_level"] == "medium"
    assert metadata["confidence"]["level"] == "high"
    assert metadata["provision_citations"] == [
        {
            "document_id": "doc-1",
            "article_num": 9,
            "clause_num": 1,
            "point_num": "a",
            "effective_status": "active",
            "retrieval_unit_id": "chunk-1",
        }
    ]
    assert metadata["historical_references"] == [
        {
            "document_id": "doc-1",
            "title": "ND 336/2025/ND-CP",
            "article_num": 9,
            "clause_num": 1,
            "point_num": "a",
            "effective_from": date(2026, 3, 1),
            "effective_to": None,
            "status": "repealed",
            "replaced_by": None,
        }
    ]


def test_build_chat_response_metadata_marks_insufficient_guardrail():
    metadata = build_chat_response_metadata(
        content=(
            "Xin lỗi, tôi chưa tìm thấy đủ căn cứ pháp lý trong dữ liệu hiện có để trả lời "
            "chắc chắn câu hỏi này.\n\nLƯU Ý PHÁP LÝ:\n..."
        ),
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        guardrail_reason="missing_citation",
    )

    assert metadata["answer_mode"] == "insufficient_evidence"
    assert metadata["confidence"]["level"] == "low"
    assert metadata["provision_citations"] == []


def test_build_chat_response_metadata_marks_clarification_direct_response():
    metadata = build_chat_response_metadata(
        content=(
            "Xin lỗi, tôi chưa hiểu rõ bạn đang muốn hỏi nội dung nào.\n\n"
            "Bạn vui lòng nói rõ thêm một trong các ý sau:"
        ),
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        guardrail_reason="query_clarification",
    )

    assert metadata["answer_mode"] == "clarification_needed"
    assert metadata["confidence"]["level"] == "low"
    assert metadata["clarification_question"] == (
        "Xin lỗi, tôi chưa hiểu rõ bạn đang muốn hỏi nội dung nào.\n\n"
        "Bạn vui lòng nói rõ thêm một trong các ý sau:"
    )


def test_build_chat_response_metadata_marks_out_of_scope_direct_response():
    metadata = build_chat_response_metadata(
        content="Xin lỗi, câu hỏi này hiện nằm ngoài phạm vi tra cứu của tôi.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=True,
        guardrail_reason="out_of_scope",
    )

    assert metadata["answer_mode"] == "out_of_scope"
    assert metadata["confidence"]["level"] == "high"


def test_build_chat_response_metadata_marks_strategy_request_high_risk():
    metadata = build_chat_response_metadata(
        content="Ban nen can nhac quy dinh lien quan va tham khao nguoi co chuyen mon neu can.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="general_legal",
        query_text="Toi nen lam gi, co nen khieu nai hay khoi kien khong?",
    )

    assert metadata["answer_mode"] == "multiple_possibilities"
    assert metadata["risk_level"] == "high"


def test_build_chat_response_metadata_marks_legal_advice_redirect_high_risk():
    metadata = build_chat_response_metadata(
        content="Toi khong the dua ra khuyen nghi chien luoc phap ly ca nhan hoa.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="general_legal",
        guardrail_reason="legal_advice_boundary",
        query_text="Toi nen kien khong?",
    )

    assert metadata["answer_mode"] == "multiple_possibilities"
    assert metadata["risk_level"] == "high"


def test_build_chat_response_metadata_marks_evidence_multiple_direct_response():
    metadata = build_chat_response_metadata(
        content="Toi thay cac can cu gan nhat dang tro toi nhieu truong hop khac nhau.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="penalty",
        guardrail_reason="evidence_multiple_possibilities",
        query_text="Xe khach don khach sai noi quy dinh bi phat bao nhieu?",
    )

    assert metadata["answer_mode"] == "multiple_possibilities"
    assert metadata["confidence"]["level"] == "medium"


def test_build_chat_response_metadata_marks_low_risk_definition_response():
    metadata = build_chat_response_metadata(
        content="Xe hop dong la loai xe van tai hanh khach theo hop dong.",
        citations=[_citation()],
        faithfulness_score=0.96,
        is_out_of_scope=False,
        query_intent="definition",
        query_text="Xe hop dong la gi?",
    )

    assert metadata["answer_mode"] == "direct"
    assert metadata["risk_level"] == "low"


def test_build_chat_response_metadata_low_confidence_is_insufficient():
    metadata = build_chat_response_metadata(
        content="Noi dung tra loi tam thoi.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="general_legal",
        query_text="Cho toi biet truong hop nay.",
        low_confidence=True,
    )

    assert metadata["answer_mode"] == "insufficient_evidence"
    assert metadata["risk_level"] == "medium"


def test_build_chat_response_metadata_uses_explicit_document_sources_for_summary():
    metadata = build_chat_response_metadata(
        content="Tom tat chuan cua van ban 35/2024/QH15.",
        citations=[],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="document_summary_standard",
        document_sources=[
            {
                "document_id": "doc-35",
                "title": "Luat Duong bo",
                "issuing_body": "Quoc hoi",
                "date": date(2024, 6, 27),
                "url": "https://example.test/35",
            }
        ],
    )

    assert metadata["answer_mode"] == "summary"
    assert metadata["document_sources"] == [
        {
            "document_id": "doc-35",
            "title": "Luat Duong bo",
            "issuing_body": "Quoc hoi",
            "date": date(2024, 6, 27),
            "url": "https://example.test/35",
        }
    ]
    assert metadata["provision_citations"] == []


def test_build_chat_response_metadata_derives_document_sources_from_citations():
    metadata = build_chat_response_metadata(
        content="Noi dung tra loi co can cu.",
        citations=[_citation()],
        faithfulness_score=0.96,
        is_out_of_scope=False,
        query_intent="general_legal",
    )

    assert metadata["document_sources"] == [
        {
            "document_id": "doc-1",
            "title": "ND 336/2025/ND-CP",
            "issuing_body": None,
            "date": date(2026, 3, 1),
            "url": None,
        }
    ]


def test_build_chat_response_metadata_keeps_historical_out_of_provision_citations():
    metadata = build_chat_response_metadata(
        content="Thong tin lich su cua van ban cu.",
        citations=[_citation(status="expired")],
        faithfulness_score=None,
        is_out_of_scope=False,
        query_intent="comparison_history",
    )

    assert metadata["answer_mode"] == "historical"
    assert metadata["provision_citations"] == []
    assert metadata["historical_references"] == [
        {
            "document_id": "doc-1",
            "title": "ND 336/2025/ND-CP",
            "article_num": 9,
            "clause_num": 1,
            "point_num": "a",
            "effective_from": date(2026, 3, 1),
            "effective_to": None,
            "status": "expired",
            "replaced_by": None,
        }
    ]
