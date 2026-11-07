"""Unit tests for citation verification (Phase 4).

No database required — tests use in-memory RetrievedChunk objects.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.rag.verification import (
    _extract_article_refs,
    _find_best_chunk,
    citations_from_retrieval_units,
    compute_faithfulness_score,
    has_hallucination,
    prune_unsupported_cited_lines,
    verify_citations,
)
from src.schemas.rag import RetrievedChunk, VerificationStatus


def _make_chunk(
    chunk_id: str = "c1",
    article_num: int = 9,
    clause_num: int | None = 1,
    point_num: str | None = None,
    text: str = "Phạt tiền từ 400.000 đến 600.000 đồng đối với hành vi vượt đèn đỏ",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id="d1",
        doc_title="NĐ 336/2025/NĐ-CP",
        chunk_type="khoan",
        article_num=article_num,
        clause_num=clause_num,
        point_num=point_num,
        status="active",
        effective_date=date(2026, 3, 1),
        text_snippet=text,
    )


class TestArticleExtraction:
    def test_extracts_single_dieu(self):
        refs = _extract_article_refs("Theo Điều 9 quy định")
        assert len(refs) == 1
        assert refs[0]["article_num"] == 9

    def test_extracts_dieu_khoan(self):
        refs = _extract_article_refs("Theo Điều 9 Khoản 2 quy định")
        assert len(refs) == 1
        assert refs[0]["article_num"] == 9
        assert refs[0]["clause_num"] == 2

    def test_extracts_dieu_khoan_diem(self):
        refs = _extract_article_refs("Theo Điều 5 Khoản 3 Điểm a quy định")
        assert len(refs) == 1
        assert refs[0]["article_num"] == 5
        assert refs[0]["clause_num"] == 3
        assert refs[0]["point_num"] == "a"

    def test_extracts_multiple_dieu(self):
        refs = _extract_article_refs("Điều 5 và Điều 9 quy định khác nhau")
        assert len(refs) == 2
        assert refs[0]["article_num"] == 5
        assert refs[1]["article_num"] == 9

    def test_no_dieu_returns_empty(self):
        refs = _extract_article_refs("Không có trích dẫn pháp lý nào")
        assert refs == []

    def test_verbose_format_between_dieu_and_khoan(self):
        # LM may insert explanation between Điều and Khoản.
        text = (
            "Theo Điều 5, trong đó quy định cụ thể về điều kiện "
            "kinh doanh vận tải hành khách bằng ô tô tại khoản 3 điểm b"
        )
        refs = _extract_article_refs(text)
        assert len(refs) == 1
        assert refs[0]["article_num"] == 5
        assert refs[0]["clause_num"] == 3
        assert refs[0]["point_num"] == "b"

    def test_two_dieu_does_not_cross_contaminate(self):
        # Khoản 2 after Điều 9 should not attach to Điều 5.
        text = "Điều 5 quy định chung. Điều 9 Khoản 2 quy định cụ thể"
        refs = _extract_article_refs(text)
        assert len(refs) == 2
        assert refs[0]["article_num"] == 5
        assert refs[0]["clause_num"] is None
        assert refs[1]["article_num"] == 9
        assert refs[1]["clause_num"] == 2

    def test_clause_in_next_bullet_does_not_attach_to_previous_article(self):
        refs = _extract_article_refs(
            "Quy định tốc độ theo Điều 9.\n- Đặt biển báo theo khoản 2 Điều 10."
        )

        assert [(ref["article_num"], ref["clause_num"]) for ref in refs] == [
            (9, None),
            (10, 2),
        ]

    @pytest.mark.parametrize("punctuation", ["?", "!"])
    def test_sentence_boundary_does_not_attach_next_clause_to_previous_article(
        self, punctuation: str
    ):
        refs = _extract_article_refs(
            f"Quy định chung nằm tại Điều 9{punctuation} Khoản 2 Điều 10 quy định trường hợp riêng."
        )

        assert [(ref["article_num"], ref["clause_num"]) for ref in refs] == [
            (9, None),
            (10, 2),
        ]

    def test_inline_bullet_does_not_attach_next_clause_to_previous_article(self):
        refs = _extract_article_refs(
            "Quy định chung tại Điều 9 • Khoản 2 Điều 10 quy định trường hợp riêng."
        )

        assert [(ref["article_num"], ref["clause_num"]) for ref in refs] == [
            (9, None),
            (10, 2),
        ]

    def test_reverse_order_with_commas(self):
        refs = _extract_article_refs(
            "Căn cứ theo Khoản 5, Điểm h, Điều 6 Nghị định 168/2024/NĐ-CP."
        )

        assert len(refs) == 1
        assert refs[0]["article_num"] == 6
        assert refs[0]["clause_num"] == 5
        assert refs[0]["point_num"] == "h"


class TestFindBestChunk:
    def test_exact_match(self):
        chunks = [_make_chunk("c1", 9, 1), _make_chunk("c2", 9, 2)]
        ref = {"article_num": 9, "clause_num": 2, "point_num": None}
        result = _find_best_chunk(ref, chunks)
        assert result is not None
        assert result.chunk_id == "c2"

    def test_wrong_clause_does_not_fallback_to_same_article(self):
        chunks = [_make_chunk("c1", 9, 1)]
        chunks[0].asset_ids = ["asset-1"]
        ref = {"article_num": 9, "clause_num": 5, "point_num": None}
        result = _find_best_chunk(ref, chunks)
        assert result is None

    def test_no_match(self):
        chunks = [_make_chunk("c1", 5, 1)]
        ref = {"article_num": 9, "clause_num": None, "point_num": None}
        result = _find_best_chunk(ref, chunks)
        assert result is None

    def test_clause_chunk_supports_point_citation(self):
        # A whole-clause chunk (point_num=None) contains all its points, so it
        # should be chosen for a point-level reference.
        chunk = _make_chunk("c1", 9, 1, point_num=None)
        ref = {"article_num": 9, "clause_num": 1, "point_num": "b"}
        result = _find_best_chunk(ref, [chunk])
        assert result is not None
        assert result.chunk_id == "c1"

    def test_exact_point_chunk_preferred_over_clause(self):
        clause = _make_chunk("c1", 9, 1, point_num=None)
        point_b = _make_chunk("c2", 9, 1, point_num="b")
        ref = {"article_num": 9, "clause_num": 1, "point_num": "b"}
        result = _find_best_chunk(ref, [clause, point_b])
        assert result is not None
        assert result.chunk_id == "c2"

    def test_document_number_disambiguates_same_article(self):
        first = _make_chunk("c1", 9, 1)
        second = _make_chunk("c2", 9, 1).model_copy(
            update={
                "doc_id": "d2",
                "doc_title": "NĐ 168/2024/NĐ-CP",
                "document_number": "168/2024/NĐ-CP",
            }
        )
        first = first.model_copy(update={"document_number": "336/2025/NĐ-CP"})
        ref = {"article_num": 9, "clause_num": 1, "point_num": None}

        result = _find_best_chunk(
            ref,
            [first, second],
            "Theo khoản 1 Điều 9 Nghị định 168/2024/NĐ-CP",
        )

        assert result is not None
        assert result.chunk_id == "c2"


class TestVerifyCitations:
    def test_inline_bullets_keep_each_document_mention_with_its_claim(self):
        first = _make_chunk(
            "first",
            9,
            1,
            text="Người điều khiển phải giảm tốc độ khi qua khu vực trường học.",
        ).model_copy(
            update={
                "doc_id": "doc-111",
                "doc_title": "Nghị định 111/2025/NĐ-CP",
                "document_number": "111/2025/NĐ-CP",
            }
        )
        second = _make_chunk(
            "second",
            9,
            1,
            text="Người điều khiển phải bật đèn khi đi trong hầm đường bộ.",
        ).model_copy(
            update={
                "doc_id": "doc-222",
                "doc_title": "Nghị định 222/2025/NĐ-CP",
                "document_number": "222/2025/NĐ-CP",
            }
        )
        answer = (
            "Phải giảm tốc độ khi qua khu vực trường học theo khoản 1 Điều 9 "
            "Nghị định 111/2025/NĐ-CP • Phải bật đèn khi đi trong hầm đường bộ theo "
            "khoản 1 Điều 9 Nghị định 222/2025/NĐ-CP."
        )

        citations = verify_citations(answer, [second, first])

        assert [citation.chunk_id for citation in citations] == ["first", "second"]
        assert all(
            citation.verification_status == VerificationStatus.verified for citation in citations
        )

    def test_internal_cross_reference_is_not_a_separate_citation(self):
        chunk = _make_chunk(
            "c1",
            4,
            2,
            text=(
                "Người dự sát hạch thực hiện bốn bài gồm hình số 8, đường thẳng, "
                "vạch cản và đường gồ ghề, trừ trường hợp tại khoản 2 Điều 5."
            ),
        )
        answer = (
            "Theo khoản 2 Điều 4, người dự sát hạch thực hiện bốn bài gồm hình "
            "số 8, đường thẳng, vạch cản và đường gồ ghề, trừ trường hợp tại "
            "khoản 2 Điều 5."
        )

        citations = verify_citations(answer, [chunk])

        assert len(citations) == 1
        assert citations[0].article_num == 4
        assert citations[0].verification_status == VerificationStatus.verified

    def test_verified_citation(self):
        chunks = [_make_chunk("c1", 9, 1)]
        chunks[0].asset_ids = ["asset-1"]
        answer = (
            "Theo Điều 9 Khoản 1, phạt tiền từ 400.000 đến 600.000 đồng đối với hành vi vượt đèn đỏ"
        )
        citations = verify_citations(answer, chunks)
        assert len(citations) == 1
        assert citations[0].verification_status == VerificationStatus.verified
        assert citations[0].chunk_id == "c1"
        assert citations[0].asset_ids == ["asset-1"]

    def test_unverified_when_no_chunk_match(self):
        chunks = [_make_chunk("c1", 5, 1)]
        answer = "Theo Điều 99 Khoản 1, cấm xe đi vào"
        citations = verify_citations(answer, chunks)
        assert len(citations) == 1
        assert citations[0].verification_status == VerificationStatus.unverified

    def test_exact_locator_does_not_verify_an_invented_amount(self):
        chunk = _make_chunk(
            "c1",
            9,
            1,
            text="Phạt tiền từ 400.000 đến 600.000 đồng đối với hành vi này.",
        )
        answer = "Theo khoản 1 Điều 9, người vi phạm bị phạt 50.000.000 đồng."

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.unverified

    def test_consolidated_document_number_is_not_treated_as_claimed_amount(self):
        chunk = _make_chunk(
            "c1",
            3,
            1,
            text=(
                "Kiểm định là việc kiểm tra, đánh giá lần đầu và định kỳ tình "
                "trạng an toàn kỹ thuật và bảo vệ môi trường của xe cơ giới."
            ),
        ).model_copy(
            update={
                "doc_title": "Văn bản hợp nhất 02/VBHN-BGTVT",
                "document_number": "02/VBHN-BGTVT",
            }
        )
        answer = (
            "Theo khoản 1 Điều 3 Văn bản hợp nhất 02/VBHN-BGTVT, kiểm định là "
            "việc kiểm tra và đánh giá tình trạng an toàn kỹ thuật, bảo vệ môi trường."
        )

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.verified

    def test_source_only_sentence_is_grounded_with_previous_claim_sentence(self):
        chunk = _make_chunk(
            "c1",
            3,
            1,
            text=(
                "Khu đông dân cư được xác định bằng biển báo bắt đầu khu đông "
                "dân cư và biển báo hết khu đông dân cư."
            ),
        )
        answer = (
            "Khu đông dân cư được nhận biết bằng biển báo bắt đầu và hết khu "
            "đông dân cư. Theo khoản 1 Điều 3."
        )

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.verified

    def test_source_only_bullet_skips_blank_line_to_previous_claim(self):
        chunk = _make_chunk(
            "c1",
            3,
            1,
            text=(
                "Kiểm định là việc kiểm tra, đánh giá lần đầu và định kỳ tình "
                "trạng an toàn kỹ thuật và bảo vệ môi trường."
            ),
        )
        answer = (
            "Kiểm định là việc kiểm tra, đánh giá lần đầu và định kỳ tình trạng "
            "an toàn kỹ thuật và bảo vệ môi trường.\n\n"
            "- Căn cứ theo khoản 1 Điều 3."
        )

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.verified

    def test_numeric_grounding_treats_zero_padded_count_as_same_number(self):
        chunk = _make_chunk(
            "c1",
            4,
            2,
            text="Người dự sát hạch phải điều khiển xe mô tô qua 04 bài sát hạch.",
        )
        answer = "Người dự sát hạch thực hiện 4 bài. Theo khoản 2 Điều 4."

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.verified

    def test_point_citation_against_clause_chunk_is_verified(self):
        # Answer cites a specific point; only the whole-clause chunk is in
        # context. Should be verified (clause contains the point), not partial.
        chunk = _make_chunk(
            "c1",
            9,
            1,
            point_num=None,
            text="Khoản 1 gồm: a) cấm vượt đèn đỏ; b) cấm chạy quá tốc độ quy định",
        )
        answer = "Theo Điều 9 Khoản 1 Điểm b, cấm chạy quá tốc độ quy định trên đường"
        citations = verify_citations(answer, [chunk])
        assert len(citations) == 1
        assert citations[0].verification_status == VerificationStatus.verified
        assert citations[0].point_num == "b"

    def test_no_citations_for_no_legal_refs(self):
        chunks = [_make_chunk("c1", 9, 1)]
        answer = "Thời tiết hôm nay đẹp"
        citations = verify_citations(answer, chunks)
        assert citations == []

    def test_document_title_mention_is_not_enough_to_verify(self):
        chunks = [_make_chunk("c1", 9, 1)]
        answer = "Nghị định 336/2025/NĐ-CP quy định mức phạt là 50 triệu đồng."

        assert verify_citations(answer, chunks) == []

    def test_verifier_uses_full_text_not_only_preview(self):
        chunk = _make_chunk("c1", 9, 1, text="Phần mở đầu không chứa mức phạt.")
        chunk = chunk.model_copy(
            update={
                "full_text": (
                    "Phần mở đầu không chứa mức phạt. "
                    "Phạt tiền từ 400.000 đến 600.000 đồng đối với hành vi vượt đèn đỏ."
                )
            }
        )
        answer = "Theo khoản 1 Điều 9, phạt tiền từ 400.000 đến 600.000 đồng khi vượt đèn đỏ."

        citations = verify_citations(answer, [chunk])

        assert citations[0].verification_status == VerificationStatus.verified

    def test_blocked_for_repealed_chunk(self):
        chunk = _make_chunk("c1", 9, 1)
        chunk = chunk.model_copy(update={"status": "repealed"})
        answer = "Theo Điều 9 Khoản 1, phạt tiền 400.000 đồng vượt đèn đỏ"
        citations = verify_citations(answer, [chunk])
        assert len(citations) == 1
        assert citations[0].verification_status == VerificationStatus.blocked

    def test_retrieval_unit_fallback_uses_structured_metadata(self):
        active = _make_chunk("c1", 9, 1).model_copy(
            update={
                "doc_id": "doc-1",
                "document_number": "36/2024/QH15",
                "rerank_score": 0.8,
            }
        )
        duplicate_doc = _make_chunk("c2", 10, 1).model_copy(
            update={"doc_id": "doc-1", "rerank_score": 0.7}
        )
        inactive = _make_chunk("c3", 11, 1).model_copy(
            update={"doc_id": "doc-2", "status": "expired", "rerank_score": 0.9}
        )

        citations = citations_from_retrieval_units([inactive, duplicate_doc, active])

        assert len(citations) == 2
        assert {c.doc_id for c in citations} == {"doc-1"}
        assert {c.chunk_id for c in citations} == {"c1", "c2"}
        assert {c.article_num for c in citations} == {9, 10}
        assert citations[0].verification_status == VerificationStatus.verified


class TestFaithfulness:
    def test_all_verified(self):
        from src.schemas.rag import Citation

        citations = [
            Citation(
                citation_id="c1",
                chunk_id="ch1",
                doc_id="d1",
                doc_title="t",
                doc_type="LUAT",
                status="active",
                effective_date=date(2026, 1, 1),
                text_snippet="x",
                verification_status=VerificationStatus.verified,
                confidence=0.9,
            )
        ]
        assert compute_faithfulness_score(citations) == 1.0

    def test_mixed_scores(self):
        from src.schemas.rag import Citation

        citations = [
            Citation(
                citation_id="c1",
                chunk_id="ch1",
                doc_id="d1",
                doc_title="t",
                doc_type="LUAT",
                status="active",
                effective_date=date(2026, 1, 1),
                text_snippet="x",
                verification_status=VerificationStatus.verified,
                confidence=0.9,
            ),
            Citation(
                citation_id="c2",
                chunk_id="ch2",
                doc_id="d1",
                doc_title="t",
                doc_type="LUAT",
                status="active",
                effective_date=date(2026, 1, 1),
                text_snippet="x",
                verification_status=VerificationStatus.unverified,
                confidence=0.1,
            ),
        ]
        score = compute_faithfulness_score(citations)
        assert 0.5 < score < 0.7

    def test_hallucination_detection_blocked(self):
        from src.schemas.rag import Citation

        citations = [
            Citation(
                citation_id="c1",
                chunk_id="ch1",
                doc_id="d1",
                doc_title="t",
                doc_type="LUAT",
                status="active",
                effective_date=date(2026, 1, 1),
                text_snippet="x",
                verification_status=VerificationStatus.blocked,
                confidence=0.0,
            ),
        ]
        assert has_hallucination(citations) is True

    def test_no_hallucination_when_verified(self):
        from src.schemas.rag import Citation

        citations = [
            Citation(
                citation_id="c1",
                chunk_id="ch1",
                doc_id="d1",
                doc_title="t",
                doc_type="LUAT",
                status="active",
                effective_date=date(2026, 1, 1),
                text_snippet="x",
                verification_status=VerificationStatus.verified,
                confidence=0.9,
            ),
        ]
        assert has_hallucination(citations) is False

    def test_any_unverified_locator_is_hallucination(self):
        from src.schemas.rag import Citation

        verified = Citation(
            citation_id="c1",
            chunk_id="ch1",
            doc_id="d1",
            doc_title="t",
            doc_type="LUAT",
            status="active",
            effective_date=date(2026, 1, 1),
            text_snippet="x",
            verification_status=VerificationStatus.verified,
            confidence=0.9,
        )
        unverified = verified.model_copy(
            update={
                "citation_id": "c2",
                "chunk_id": "",
                "doc_id": "",
                "verification_status": VerificationStatus.unverified,
                "confidence": 0.0,
            }
        )

        assert has_hallucination([verified, verified, unverified]) is True

    def test_prunes_only_line_with_unsupported_legal_locator(self):
        chunks = [
            RetrievedChunk(
                chunk_id="chunk-1",
                doc_id="doc-1",
                doc_title="Thông tư 12/2025/TT-BCA",
                doc_type="THONG_TU",
                chunk_type="khoan",
                status="active",
                effective_date=date(2025, 3, 1),
                article_num=4,
                clause_num=1,
                point_num=None,
                text_snippet="Sát hạch lý thuyết gồm câu hỏi về pháp luật giao thông và kỹ thuật lái xe.",
                full_text="Sát hạch lý thuyết gồm câu hỏi về pháp luật giao thông và kỹ thuật lái xe.",
                source_url=None,
                vector_score=0.9,
                fts_score=0.9,
                hybrid_score=0.9,
            )
        ]
        answer = (
            "Phần lý thuyết kiểm tra kiến thức pháp luật giao thông và kỹ thuật lái xe.\n"
            "- Sát hạch lý thuyết gồm kiến thức pháp luật giao thông và kỹ thuật lái xe "
            "theo khoản 1 Điều 4.\n"
            "- Người dự thi được miễn phần này theo khoản 2 Điều 4."
        )

        pruned = prune_unsupported_cited_lines(answer, chunks)

        assert "khoản 1 Điều 4" in pruned
        assert "khoản 2 Điều 4" not in pruned
