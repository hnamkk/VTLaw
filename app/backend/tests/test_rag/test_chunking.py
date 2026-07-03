"""Tests for structure detection and the hierarchical chunker (spec 10).

These run without a DB or network — they assert the structural contract:
correct hierarchy, full legal path, no empty chunks, enriched embedding_content.
"""

from __future__ import annotations

from src.core.config import settings
from src.rag.chunking import DocMeta, chunk_document
from src.rag.chunking.base import (
    CHUNK_TYPE_CHUONG,
    CHUNK_TYPE_DIEM,
    CHUNK_TYPE_DIEU,
    CHUNK_TYPE_KHOAN,
    CHUNK_TYPE_PHU_LUC,
)
from src.rag.chunking.structure import MarkerKind, classify_line, roman_to_int
from src.rag.ingestion import _validate_chunk_hierarchy
from src.rag.parsing.base import BlockKind, ParsedBlock, ParseResult

META = DocMeta(
    title="NĐ 168/2024/NĐ-CP",
    doc_type="NGHI_DINH",
    effective_date="2025-01-01",
    status="active",
)


def _parsed(*lines: str) -> ParseResult:
    blocks = [ParsedBlock(text=ln, kind=BlockKind.text) for ln in lines]
    return ParseResult(blocks=blocks, confidence=1.0)


# --------------------------------------------------------------------------- #
# structure detection
# --------------------------------------------------------------------------- #
def test_roman_to_int():
    assert roman_to_int("II") == 2
    assert roman_to_int("IV") == 4
    assert roman_to_int("XIV") == 14
    assert roman_to_int("foo") is None


def test_classify_chuong_dieu_khoan_diem():
    assert classify_line("Chương II QUY ĐỊNH CHUNG").kind is MarkerKind.chuong
    assert classify_line("Điều 9. Điều kiện của người lái xe").kind is MarkerKind.dieu
    assert classify_line("1. Người lái xe phải đủ tuổi").kind is MarkerKind.khoan
    assert classify_line("a) Có giấy phép lái xe").kind is MarkerKind.diem


def test_dieu_not_misread_as_khoan():
    m = classify_line("Điều 9. Điều kiện")
    assert m.kind is MarkerKind.dieu
    assert m.number == 9


# --------------------------------------------------------------------------- #
# chunker
# --------------------------------------------------------------------------- #
def test_khoan_is_primary_chunk_with_full_path():
    parsed = _parsed(
        "Chương II QUY ĐỊNH VỀ NGƯỜI LÁI XE",
        "Điều 9. Điều kiện của người lái xe tham gia giao thông",
        "1. Người lái xe tham gia giao thông đường bộ phải đủ độ tuổi, sức khỏe "
        "theo quy định của pháp luật và có giấy phép lái xe phù hợp.",
        "2. Người tập lái xe phải thực hành trên xe tập lái và có giáo viên bảo trợ tay lái.",
    )
    chunks = chunk_document(parsed, META)
    khoan = [c for c in chunks if c.chunk_type == CHUNK_TYPE_KHOAN]
    assert len(khoan) == 2
    c1 = khoan[0]
    assert c1.article_num == 9
    assert c1.clause_num == 1
    assert c1.chapter_num == 2
    assert "Chương 2" in c1.heading_path[0]
    assert "Điều 9" in c1.heading_path[1]
    assert META.title in c1.display_path
    assert "Khoản 1" in c1.display_path


def test_embedding_content_has_header_and_path():
    parsed = _parsed(
        "Điều 5. Quy tắc chung",
        "1. Người tham gia giao thông phải chấp hành quy tắc giao thông đường bộ "
        "và hiệu lệnh của người điều khiển giao thông một cách nghiêm túc.",
    )
    chunk = chunk_document(parsed, META)[0]
    head = chunk.embedding_content.splitlines()[0]
    assert META.title in head
    assert "NGHI_DINH" in head
    assert "2025-01-01" in head
    assert "active" in head
    assert "Điều 5" in chunk.embedding_content


def test_no_empty_chunks():
    parsed = _parsed(
        "Điều 1. Phạm vi điều chỉnh",  # heading only, no body -> dropped
        "Điều 2. Đối tượng áp dụng",
        "1. Nghị định này áp dụng đối với cơ quan, tổ chức, cá nhân có liên quan "
        "đến trật tự, an toàn giao thông đường bộ trên lãnh thổ Việt Nam.",
    )
    chunks = chunk_document(parsed, META)
    assert all(c.text_content.strip() for c in chunks)
    # Điều 1 had no intro text and no clauses -> no bare dieu chunk emitted.
    assert not any(c.chunk_type == CHUNK_TYPE_DIEU and c.article_num == 1 for c in chunks)


def test_dieu_intro_text_becomes_chunk():
    parsed = _parsed(
        "Điều 3. Giải thích từ ngữ",
        "Trong Nghị định này, các từ ngữ dưới đây được hiểu thống nhất như sau "
        "để bảo đảm áp dụng đúng phạm vi điều chỉnh của văn bản quy phạm.",
    )
    chunks = chunk_document(parsed, META)
    dieu = [c for c in chunks if c.chunk_type == CHUNK_TYPE_DIEU]
    assert len(dieu) == 1
    assert dieu[0].article_num == 3


def test_long_chunk_is_split_preserving_path():
    long_body = "Quy định chi tiết. " * 200  # ~3800 chars, over CHUNK_MAX_LEN
    parsed = _parsed("Điều 7. Quy định dài", f"1. {long_body}")
    chunks = chunk_document(parsed, META)
    khoan = [c for c in chunks if c.chunk_type == CHUNK_TYPE_KHOAN]
    assert len(khoan) >= 2
    for c in khoan:
        assert len(c.text_content) <= settings.CHUNK_MAX_LEN
        assert c.article_num == 7
        assert "Điều 7" in c.heading_path[-1]


def test_short_chunk_keeps_its_own_locator():
    parsed = _parsed(
        "Điều 4. Nguyên tắc",
        "1. Đây là một khoản có nội dung đủ dài để vượt qua ngưỡng tối thiểu "
        "tám mươi ký tự nhằm không bị gộp vào khoản khác trong quá trình chuẩn hóa.",
        "2. Ngắn.",
    )
    chunks = chunk_document(parsed, META)
    art4 = [c for c in chunks if c.article_num == 4]
    assert len(art4) == 2
    assert [chunk.clause_num for chunk in art4] == [1, 2]
    assert art4[1].text_content == "Ngắn."
    assert art4[1].display_path.endswith("Khoản 2")


def test_short_chunk_path_preserves_title_containing_khoan():
    title_meta = DocMeta(
        title="Quy định về Khoản vay",  # title contains "Khoản"
        doc_type="LUAT",
        effective_date="2025-01-01",
        status="active",
    )
    parsed = _parsed(
        "Điều 4. Nguyên tắc",
        "1. Đây là một khoản có nội dung đủ dài để vượt qua ngưỡng tối thiểu "
        "tám mươi ký tự nhằm không bị gộp vào khoản khác trong quá trình chuẩn hóa.",
        "2. Ngắn.",
    )
    chunks = chunk_document(parsed, title_meta)
    assert len(chunks) == 2
    assert all("Quy định về Khoản vay" in chunk.display_path for chunk in chunks)
    assert chunks[0].display_path.endswith("Khoản 1")
    assert chunks[1].display_path.endswith("Khoản 2")


def test_table_becomes_phu_luc_chunk():
    parsed = ParseResult(
        blocks=[
            ParsedBlock(text="Điều 6. Mức phạt", kind=BlockKind.text),
            ParsedBlock(
                text="Hành vi | Mức phạt\nVượt đèn đỏ | 4.000.000 - 6.000.000 đồng",
                kind=BlockKind.table,
            ),
        ],
        confidence=1.0,
    )
    chunks = chunk_document(parsed, META)
    tables = [c for c in chunks if c.chunk_type == CHUNK_TYPE_PHU_LUC]
    assert len(tables) == 1
    assert "Vượt đèn đỏ" in tables[0].text_content
    assert tables[0].article_num == 6


def test_preamble_and_source_order_are_preserved():
    parsed = _parsed(
        "QUỐC HỘI",
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
        "Độc lập - Tự do - Hạnh phúc",
        "Luật số: 118/2025/QH15",
        "Điều 1. Phạm vi điều chỉnh",
        "1. Luật này sửa đổi, bổ sung một số điều của các luật có liên quan.",
    )
    chunks = chunk_document(parsed, META)

    assert chunks[0].content_kind == "preamble"
    assert "QUỐC HỘI" in chunks[0].text_content
    assert chunks[0].source_order == 0
    assert chunks[1].article_num == 1
    assert chunks[1].source_order == 1
    assert [chunk.source_order for chunk in chunks] == list(range(len(chunks)))


def test_numbered_consolidation_notes_before_first_article_stay_preamble():
    parsed = _parsed(
        "VAN BAN HOP NHAT",
        "1. Thong tu so 02/2023/TT-BGTVT sua doi Thong tu so 16/2021/TT-BGTVT.",
        "2. Thong tu so 08/2023/TT-BGTVT tiep tuc sua doi, bo sung.",
        "a) Ghi chu hop nhat duoc giu nguyen theo van ban nguon.",
        "Điều 1. Phạm vi điều chỉnh",
        "1. Thong tu nay quy dinh ve kiem dinh an toan ky thuat phuong tien.",
    )

    chunks = chunk_document(parsed, META)

    assert chunks[0].chunk_type == CHUNK_TYPE_PHU_LUC
    assert chunks[0].content_kind == "preamble"
    assert "1. Thong tu so 02/2023/TT-BGTVT" in chunks[0].text_content
    assert "2. Thong tu so 08/2023/TT-BGTVT" in chunks[0].text_content
    assert "a) Ghi chu hop nhat" in chunks[0].text_content
    assert chunks[0].article_num is None
    assert chunks[1].chunk_type == CHUNK_TYPE_KHOAN
    assert chunks[1].article_num == 1
    assert chunks[1].clause_num == 1
    assert all(
        chunk.article_num is not None
        for chunk in chunks
        if chunk.chunk_type in {CHUNK_TYPE_DIEU, CHUNK_TYPE_KHOAN, CHUNK_TYPE_DIEM}
    )
    _validate_chunk_hierarchy(chunks)


# --------------------------------------------------------------------------- #
# Chương chunk (spec 10 §4 — only when chapter has its own description)
# --------------------------------------------------------------------------- #
def test_chuong_with_description_becomes_chunk():
    parsed = _parsed(
        "Chương I NHỮNG QUY ĐỊNH CHUNG",
        "Chương này quy định các nguyên tắc cơ bản về trật tự an toàn giao thông "
        "đường bộ, áp dụng thống nhất trên phạm vi toàn quốc cho mọi đối tượng.",
        "Điều 1. Phạm vi điều chỉnh",
        "1. Nghị định này quy định chi tiết các hành vi vi phạm hành chính trong "
        "lĩnh vực giao thông đường bộ và mức xử phạt tương ứng theo quy định.",
    )
    chunks = chunk_document(parsed, META)
    chuong = [c for c in chunks if c.chunk_type == CHUNK_TYPE_CHUONG]
    assert len(chuong) == 1
    assert chuong[0].chapter_num == 1
    assert "Chương 1" in chuong[0].heading_path[0]
    assert "nguyên tắc cơ bản" in chuong[0].text_content


def test_chuong_without_description_emits_no_chunk():
    parsed = _parsed(
        "Chương I NHỮNG QUY ĐỊNH CHUNG",  # heading only, straight into Điều
        "Điều 1. Phạm vi điều chỉnh",
        "1. Nghị định này quy định chi tiết các hành vi vi phạm hành chính trong "
        "lĩnh vực giao thông đường bộ và mức xử phạt tương ứng theo quy định.",
    )
    chunks = chunk_document(parsed, META)
    assert not any(c.chunk_type == CHUNK_TYPE_CHUONG for c in chunks)


# --------------------------------------------------------------------------- #
# Điểm chunk (spec 10 §4 — long multi-point clause splits along points)
# --------------------------------------------------------------------------- #
def test_multi_point_clause_clears_point_num():
    parsed = _parsed(
        "Điều 8. Các hành vi bị nghiêm cấm",
        "1. Nghiêm cấm các hành vi sau đây khi tham gia giao thông đường bộ:",
        "a) Điều khiển xe khi trong máu có nồng độ cồn vượt mức cho phép.",
        "b) Điều khiển xe chạy quá tốc độ quy định trên từng tuyến đường.",
    )
    chunks = chunk_document(parsed, META)
    khoan = [c for c in chunks if c.chunk_type == CHUNK_TYPE_KHOAN and c.clause_num == 1]
    assert len(khoan) == 1
    # A clause spanning multiple points must not claim to be a single point.
    assert khoan[0].point_num is None
    assert "a)" in khoan[0].text_content
    assert "b)" in khoan[0].text_content


def test_long_multi_point_clause_splits_into_diem_chunks():
    long_point = "Nội dung điểm rất dài cần được tách riêng. " * 40  # ~1700 chars
    parsed = _parsed(
        "Điều 10. Quy định chi tiết",
        "1. Khoản này gồm nhiều điểm dài:",
        f"a) {long_point}",
        f"b) {long_point}",
    )
    chunks = chunk_document(parsed, META)
    diem = [c for c in chunks if c.chunk_type == CHUNK_TYPE_DIEM]
    # The over-length clause splits along its point boundaries.
    assert len(diem) >= 2
    points = {c.point_num for c in diem}
    assert "a" in points
    assert "b" in points
    for c in diem:
        assert c.article_num == 10
        assert c.clause_num == 1
        assert len(c.text_content) <= settings.CHUNK_MAX_LEN
