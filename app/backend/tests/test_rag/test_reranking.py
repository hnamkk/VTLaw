"""Unit tests for deterministic local legal ranking."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from src.rag import reranking as reranking_module
from src.rag.reranking import rerank_chunks
from src.schemas.rag import RetrievedChunk


def _chunk(
    chunk_id: str,
    text: str,
    *,
    article: int,
    clause: int = 1,
    hybrid: float = 0.5,
    document_number: str = "336/2025/NĐ-CP",
    section_path: list[str] | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id=f"doc-{chunk_id}",
        doc_title=f"Nghị định {document_number}",
        doc_type="NGHI_DINH",
        document_number=document_number,
        chunk_type="khoan",
        article_num=article,
        clause_num=clause,
        section_path=section_path or [],
        status="active",
        effective_date=date(2026, 1, 1),
        text_snippet=text[:500],
        full_text=text,
        vector_score=0.7,
        fts_score=0.6,
        hybrid_score=hybrid,
    )


@pytest.mark.asyncio
async def test_local_ranker_prioritizes_matching_legal_content():
    relevant = _chunk(
        "relevant",
        "Phạt tiền người điều khiển xe mô tô vượt đèn tín hiệu đỏ.",
        article=9,
        hybrid=0.6,
    )
    unrelated = _chunk(
        "unrelated",
        "Quy định về giấy phép kinh doanh vận tải hành khách.",
        article=20,
        hybrid=0.8,
    )

    result = await rerank_chunks("Mức phạt xe máy vượt đèn đỏ theo Điều 9?", [unrelated, relevant])

    assert result.reranker_used is True
    assert result.reranker_failed is False
    assert result.error_code is None
    assert result.chunks[0].chunk_id == "relevant"
    assert result.chunks[0].rerank_score > result.chunks[1].rerank_score


@pytest.mark.asyncio
async def test_local_ranker_generalizes_to_unseen_legal_intent():
    relevant = _chunk(
        "animal-transport",
        "Phương tiện vận chuyển động vật sống phải bảo đảm vệ sinh và an toàn khi qua hầm đường bộ.",
        article=18,
        hybrid=0.48,
    )
    unrelated = _chunk(
        "passenger-license",
        "Điều kiện cấp giấy phép kinh doanh vận tải hành khách bằng xe ô tô.",
        article=12,
        hybrid=0.72,
    )

    result = await rerank_chunks(
        "Điều kiện vận chuyển động vật sống qua hầm đường bộ là gì?",
        [unrelated, relevant],
    )

    assert result.chunks[0].chunk_id == "animal-transport"


@pytest.mark.asyncio
async def test_local_ranker_prioritizes_exact_document_and_clause():
    exact = _chunk("exact", "Điều kiện áp dụng tại khoản này.", article=12, clause=3)
    other = _chunk(
        "other",
        "Điều kiện áp dụng tại khoản khác.",
        article=12,
        clause=1,
        document_number="168/2024/NĐ-CP",
    )

    result = await rerank_chunks(
        "Khoản 3 Điều 12 Nghị định 336/2025/NĐ-CP quy định gì?", [other, exact]
    )

    assert result.chunks[0].chunk_id == "exact"


@pytest.mark.asyncio
async def test_local_ranker_prefers_direct_definition_over_related_rule():
    definition = _chunk(
        "definition",
        "Kết cấu hạ tầng đường bộ bao gồm công trình đường bộ, bến xe, bãi đỗ xe và hành lang an toàn đường bộ.",
        article=2,
        hybrid=0.48,
    )
    related = _chunk(
        "related",
        "Trách nhiệm quản lý, bảo vệ và khai thác kết cấu hạ tầng đường bộ.",
        article=15,
        hybrid=0.62,
    )

    result = await rerank_chunks(
        "Kết cấu hạ tầng đường bộ bao gồm những thành phần nào?",
        [related, definition],
    )

    assert result.chunks[0].chunk_id == "definition"


@pytest.mark.asyncio
async def test_local_ranker_prefers_document_scope_provision():
    scope = _chunk(
        "scope",
        "Thông tư này quy định về tốc độ thiết kế, tốc độ khai thác và khoảng cách an toàn.",
        article=1,
        hybrid=0.45,
    )
    detail = _chunk(
        "detail",
        "Quy định chi tiết tốc độ khai thác đối với một loại đường cụ thể.",
        article=10,
        hybrid=0.62,
    )

    result = await rerank_chunks("Thông tư này quy định những vấn đề chính nào?", [detail, scope])

    assert result.chunks[0].chunk_id == "scope"


@pytest.mark.asyncio
async def test_local_ranker_uses_article_heading_to_distinguish_vehicle_type():
    motorcycle = _chunk(
        "motorcycle",
        "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
        article=7,
        section_path=["Điều 7: Xử phạt người điều khiển xe mô tô, xe gắn máy"],
    )
    special_vehicle = _chunk(
        "special-vehicle",
        "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
        article=8,
        hybrid=0.55,
        section_path=["Điều 8: Xử phạt người điều khiển xe máy chuyên dùng"],
    )

    result = await rerank_chunks(
        "mức phạt xe mô tô xe gắn máy không chấp hành đèn tín hiệu giao thông",
        [special_vehicle, motorcycle],
    )

    assert result.chunks[0].chunk_id == "motorcycle"


@pytest.mark.asyncio
async def test_local_ranker_distinguishes_car_from_motorcycle_article():
    car = _chunk(
        "car",
        "Sử dụng điện thoại khi điều khiển phương tiện.",
        article=6,
        section_path=["Điều 6: Xử phạt người điều khiển xe ô tô, xe tải"],
    )
    motorcycle = _chunk(
        "motorcycle-phone",
        "Sử dụng điện thoại khi điều khiển phương tiện.",
        article=7,
        hybrid=0.55,
        section_path=["Điều 7: Xử phạt người điều khiển xe mô tô, xe gắn máy"],
    )

    result = await rerank_chunks(
        "xe ô tô sử dụng điện thoại khi điều khiển phương tiện",
        [motorcycle, car],
    )

    assert result.chunks[0].chunk_id == "car"


@pytest.mark.asyncio
async def test_local_ranker_is_deterministic_and_bounded():
    chunks = [
        _chunk(str(index), f"Nội dung giao thông {index}", article=index) for index in range(5)
    ]
    first = await rerank_chunks("quy định giao thông", chunks, top_k=3)
    second = await rerank_chunks("quy định giao thông", chunks, top_k=3)

    assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
    assert len(first.chunks) == 3
    assert all(0.0 <= (chunk.rerank_score or 0.0) <= 1.0 for chunk in first.chunks)


@pytest.mark.asyncio
async def test_empty_candidates_are_low_confidence():
    result = await rerank_chunks("mức phạt", [])

    assert result.chunks == []
    assert result.reranker_used is False
    assert result.low_confidence is True


@pytest.mark.asyncio
async def test_low_confidence_threshold_is_configurable():
    chunk = _chunk("weak", "nội dung không liên quan", article=1, hybrid=0.0)
    with patch("src.rag.reranking.settings.LOCAL_RANK_MIN_SCORE", 0.95):
        result = await rerank_chunks("mức phạt vượt đèn đỏ", [chunk])

    assert result.low_confidence is True


@pytest.mark.asyncio
async def test_ranker_requires_no_external_credentials_or_network():
    chunk = _chunk("local", "mức phạt vượt đèn đỏ", article=9)

    result = await rerank_chunks("mức phạt vượt đèn đỏ", [chunk])

    assert result.reranker_failed is False
    assert result.error_code is None


@pytest.mark.asyncio
async def test_ranker_materializes_candidate_text_once_per_chunk():
    chunks = [
        _chunk(str(index), f"Quy định vận tải đường bộ số {index}", article=index + 1)
        for index in range(6)
    ]

    with patch(
        "src.rag.reranking._candidate_text",
        wraps=reranking_module._candidate_text,
    ) as candidate_text:
        await rerank_chunks("quy định vận tải đường bộ", chunks)

    assert candidate_text.call_count == len(chunks)
