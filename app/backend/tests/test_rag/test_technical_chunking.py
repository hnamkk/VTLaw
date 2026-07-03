from __future__ import annotations

from src.rag.chunking import DocMeta, chunk_document
from src.rag.chunking.technical import normalize_sign_code
from src.rag.parsing.base import ParsedBlock, ParseResult


def test_normalize_sign_code_variants():
    assert normalize_sign_code("P102") == "P.102"
    assert normalize_sign_code("p-123b") == "P.123b"


def test_qcvn_chunker_preserves_section_and_sign_code():
    parsed = ParseResult(
        blocks=[
            ParsedBlock(text="PHẦN 2 QUY ĐỊNH KỸ THUẬT"),
            ParsedBlock(text="36.1 Biển báo cấm"),
            ParsedBlock(text="Biển P.123b dùng để báo cấm rẽ phải."),
        ]
    )
    meta = DocMeta(
        title="Quy chuẩn báo hiệu đường bộ",
        document_number="QCVN 41:2019/BGTVT",
        doc_type="QUY_CHUAN",
        effective_date="2020-07-01",
        status="active",
        corpus="road_technical",
        parser_profile="qcvn",
    )
    chunks = chunk_document(parsed, meta)
    assert len(chunks) == 1
    assert chunks[0].section_number == "36.1"
    assert chunks[0].sign_codes == ["P.123b"]
    assert chunks[0].locator_type == "sign_code"
    assert "QCVN 41:2019/BGTVT" in chunks[0].embedding_content


def test_qcvn_chunker_keeps_locator_label_within_db_limit_for_many_sign_codes():
    sign_codes = [
        "I.407a",
        "P.101",
        "P.102",
        "P.103",
        "P.103a",
        "P.103b",
        "P.103c",
        "P.104",
        "P.105",
        "P.106",
        "P.106a",
        "P.106b",
        "P.106c",
        "P.107",
        "P.107a",
        "P.107b",
        "P.108",
        "P.108a",
        "P.109",
        "P.110",
        "P.111",
        "P.112",
        "P.113",
        "P.114",
        "P.115",
        "P.116",
        "P.117",
        "P.118",
        "P.119",
        "P.120",
        "P.121",
        "P.122",
        "P.123",
        "P.124",
        "P.125",
        "P.126",
        "P.127",
        "P.133",
        "P.135",
        "R.302",
        "R.420",
        "R.421",
        "S.501",
        "S.503d",
        "S.509",
        "W.239b",
    ]
    parsed = ParseResult(
        blocks=[
            ParsedBlock(text="PHẦN 4 TỔ CHỨC THỰC HIỆN"),
            ParsedBlock(text="90.4 Trong quá trình thực hiện quy chuẩn"),
            ParsedBlock(text=" ".join(sign_codes)),
        ]
    )
    meta = DocMeta(
        title="Quy chuẩn báo hiệu đường bộ",
        document_number="QCVN 41:2019/BGTVT",
        doc_type="QUY_CHUAN",
        effective_date="2020-07-01",
        status="active",
        corpus="road_technical",
        parser_profile="qcvn",
    )

    chunk = chunk_document(parsed, meta)[0]

    assert len(chunk.locator_label or "") <= 180
    assert chunk.locator_label and chunk.locator_label.startswith("Biển 46 mã:")
    assert chunk.locator_label.endswith("…")
    assert chunk.sign_codes == sorted(sign_codes)


def test_qcvn_chunker_does_not_use_article_locator():
    parsed = ParseResult(blocks=[ParsedBlock(text="3.1 Thuật ngữ và định nghĩa")])
    meta = DocMeta(
        title="QCVN",
        doc_type="QUY_CHUAN",
        effective_date="2020-07-01",
        status="active",
        parser_profile="qcvn",
    )
    chunk = chunk_document(parsed, meta)[0]
    assert chunk.article_num is None
    assert chunk.locator_type == "section"
