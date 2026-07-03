from __future__ import annotations

from src.rag.intent import classify_query_intent


def test_classify_document_summary_standard():
    result = classify_query_intent("tóm tắt văn bản 35/2024/QH15")

    assert result.query_intent == "document_summary_standard"
    assert result.document_number == "35/2024/QH15"


def test_classify_definition():
    result = classify_query_intent("đường cao tốc là gì")

    assert result.query_intent == "definition"


def test_classify_obligation():
    result = classify_query_intent("đi xe máy có phải đội mũ không")

    assert result.query_intent == "obligation"


def test_classify_penalty():
    result = classify_query_intent("không đội mũ bị phạt bao nhiêu")

    assert result.query_intent == "penalty"


def test_classify_procedure():
    result = classify_query_intent("đổi GPLX cần gì")

    assert result.query_intent == "procedure"


def test_classify_effective_status():
    result = classify_query_intent("văn bản 36/2024/QH15 còn hiệu lực không")

    assert result.query_intent == "effective_status"
    assert result.document_number == "36/2024/QH15"


def test_classify_document_lookup():
    result = classify_query_intent("nội dung 36/2024/QH15")

    assert result.query_intent == "document_lookup"
    assert result.document_number == "36/2024/QH15"


def test_classify_comparison_history():
    result = classify_query_intent("trước đây quy định này thế nào")

    assert result.query_intent == "comparison_history"


def test_classify_ambiguous_short_query():
    result = classify_query_intent("quy định này")

    assert result.query_intent == "ambiguous"
