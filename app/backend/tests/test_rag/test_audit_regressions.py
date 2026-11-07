"""Adversarial regressions from the RAG audit (synthetic, not legal ground truth)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from eval.run_eval import grade_answer_faithfulness

from src.rag.agent.nodes import _structured_retrieval_answer, verify_citation_node
from src.rag.guardrails import evaluate_input_guardrail
from src.rag.prompts import PROMPT_INJECTION_TEMPLATE, classify_conversational_intent
from src.rag.retrieval.hybrid_legal import _exact_match_score, _vector_search
from src.rag.retrieval.scope import classify_scope, is_small_talk_query
from src.rag.verification import has_hallucination, verify_citations
from src.schemas.rag import RetrievedChunk, ScopeLabel


def test_exact_lookup_prefers_subject_definition_over_incidental_definition():
    def row(text):
        return SimpleNamespace(text=text, document_number="", doc_title="", citation_label="")

    direct = row("Đường thử nghiệm là đường dành cho thử nghiệm phương tiện.")
    incidental = row("Đường thử nghiệm phục vụ trung tâm quản lý, là một đơn vị vận hành.")
    terms = ("duong", "thu", "nghiem")
    assert _exact_match_score(direct, terms, set(), definition_intent=True) > (
        _exact_match_score(incidental, terms, set(), definition_intent=True)
    )


def chunk(**changes):
    values = dict(chunk_id="unit-1", doc_id="doc-1", doc_title="Văn bản thử nghiệm 1/2026/QH15",
                  document_number="1/2026/QH15", doc_type="LUAT", chunk_type="khoan",
                  status="active", effective_date=date(2026, 1, 1), article_num=9,
                  clause_num=1, text_snippet="Phạt tiền từ 400.000 đồng đến 600.000 đồng đối với hành vi vượt đèn đỏ.")
    values.update(changes)
    return RetrievedChunk(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [
    "Theo Điều 999 khoản 1, phạt tiền 10 triệu đồng.",
    "Có thể tách các căn cứ liên quan: Điều 999 phạt 10 triệu đồng.",
    "Bạn bị phạt 99 triệu đồng.",
])
async def test_generated_answer_cannot_borrow_citations(answer):
    result = await verify_citation_node({"query": "Xe máy bị phạt bao nhiêu?", "llm_output": answer,
                                         "retrieved_contexts": [chunk()]})
    assert not result["verified_citations"]


def test_wrong_document_with_same_locator_is_not_verified():
    assert has_hallucination(verify_citations(
        "Theo Điều 9 khoản 1 văn bản 2/2026/QH15, phạt tiền từ 400.000 đồng đến 600.000 đồng.", [chunk()]
    ))


def test_repeated_citation_does_not_hide_later_unsupported_amount():
    answer = ("Theo Điều 9 khoản 1, phạt tiền từ 400.000 đồng đến 600.000 đồng.\n"
              "Theo Điều 9 khoản 1, phạt tiền 999.000.000 đồng.")
    assert has_hallucination(verify_citations(answer, [chunk()]))


@pytest.mark.asyncio
async def test_source_excerpt_keeps_sibling_provisions_and_complete_conditions():
    tail = " Ngoại lệ: không áp dụng cho trường hợp cứu hộ."
    first = chunk(full_text="Nội dung: " + "Điều kiện áp dụng. " * 40 + tail)
    second = chunk(chunk_id="unit-2", clause_num=2)
    answer = _structured_retrieval_answer([first, second])
    result = await verify_citation_node({"llm_output": answer, "retrieved_contexts": [first, second]})
    assert tail in answer
    assert {c.chunk_id for c in result["verified_citations"]} == {"unit-1", "unit-2"}


@pytest.mark.parametrize("question", ["Mức phí đăng kiểm ô tô?", "Biển cấm dừng có ý nghĩa gì?",
                                      "Quy định ngày 30/06/2026 về xe máy?", "GPLX hạng A1 áp dụng theo văn bản nào?"])
def test_input_policy_does_not_memorize_golden_questions(question):
    assert evaluate_input_guardrail(question).allowed


@pytest.mark.parametrize("question", ["Xin chào bạn nhé", "Cảm ơn bạn rất nhiều", "Hello bạn"])
def test_friendly_social_variants(question):
    assert is_small_talk_query(question)


def test_greeting_and_legal_question_is_not_swallowed():
    question = "Chào bạn, xe máy vượt đèn đỏ?"
    assert not is_small_talk_query(question)
    assert classify_conversational_intent("Bạn là ai, và xe máy vượt đèn đỏ bị phạt thế nào?") is None


def test_introduction_and_unicode_response():
    assert classify_conversational_intent("Bạn có thể giới thiệu về mình không?")[0] == "assistant_identity"
    assert "???" not in PROMPT_INJECTION_TEMPLATE
    assert "kiểm chứng" in PROMPT_INJECTION_TEMPLATE


@pytest.mark.asyncio
async def test_sign_code_is_in_scope_without_embedding():
    assert (await classify_scope("Biển P.130 có ý nghĩa gì?")).label == ScopeLabel.in_scope


@pytest.mark.asyncio
async def test_historical_branch_never_executes_vector_search():
    db = AsyncMock()
    assert await _vector_search(db, query_embedding=[0.1], query_date=date(2025, 1, 1),
                                top_k=5, document_ids=None, mode="historical") == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(("response", "expected"), [
    ('{"claims":[{"supported":true},{"supported":false}]}', 0.5),
    ('{"claims":[{"supported":"true"}]}', None),
    ('not json', None), ('{"claims":[]}', 0.0),
])
async def test_evaluator_is_independent_and_fails_closed(response, expected):
    judge = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=response)))
    assert await grade_answer_faithfulness(judge, "Synthetic answer", [chunk()]) == expected
