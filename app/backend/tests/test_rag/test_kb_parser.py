from src.legal_kb.parser import build_canonical_nodes
from src.legal_kb.retrieval_units import node_is_answerable
from src.rag.chunking import ChunkDraft


def test_legal_kb_parser_restores_article_parent_for_clause_first_articles():
    drafts = [
        ChunkDraft(
            text_content="Quy định chung",
            chunk_type="chuong",
            chapter_num=1,
            heading_path=["Chương 1"],
        ),
        ChunkDraft(
            text_content="Phạm vi áp dụng.",
            chunk_type="khoan",
            chapter_num=1,
            article_num=1,
            clause_num=1,
            heading_path=["Chương 1", "Điều 1: Phạm vi điều chỉnh"],
        ),
        ChunkDraft(
            text_content="Đối tượng áp dụng.",
            chunk_type="dieu",
            chapter_num=1,
            article_num=2,
            heading_path=["Chương 1", "Điều 2: Đối tượng áp dụng"],
        ),
    ]

    nodes = build_canonical_nodes(revision_id="revision-1", drafts=drafts, parser_confidence=1.0)

    articles = [node for node in nodes if node.node_type == "article"]
    clause = next(node for node in nodes if node.node_type == "clause")
    assert [node.label for node in articles] == ["Dieu 1", "Dieu 2"]
    assert articles[0].text == "Phạm vi điều chỉnh"
    assert articles[0].structured_content["structural_only"] is True
    assert articles[0].structured_content["answerable"] is False
    assert node_is_answerable(articles[0]) is False
    assert clause.parent_id == articles[0].node_id


def test_legal_kb_parser_never_creates_legal_articles_inside_appendix():
    drafts = [
        ChunkDraft(
            text_content="Điều khoản thi hành.",
            chunk_type="dieu",
            chapter_num=7,
            article_num=43,
            heading_path=["Chương 7", "Điều 43: Trách nhiệm thi hành"],
        ),
        ChunkDraft(
            text_content="Phụ lục I: Trình tự sát hạch lái xe.",
            chunk_type="khoan",
            chapter_num=6,
            article_num=40,
            clause_num=1,
            heading_path=["Chương 6", "Điều 40: Các phụ lục kèm theo"],
        ),
        ChunkDraft(
            text_content="Hiệu lực thi hành.",
            chunk_type="khoan",
            chapter_num=7,
            article_num=41,
            clause_num=1,
            heading_path=["Chương 7", "Điều 41: Hiệu lực thi hành"],
        ),
        ChunkDraft(
            text_content="Phụ lục VII\nBiểu mẫu chuẩn bị kỳ sát hạch",
            chunk_type="phu_luc",
            chapter_num=7,
            article_num=41,
            heading_path=["Chương 7", "Điều 41: Hiệu lực thi hành"],
        ),
        ChunkDraft(
            text_content="Cho phép tổ chức kỳ sát hạch.",
            chunk_type="dieu",
            chapter_num=7,
            article_num=1,
            heading_path=["Chương 7", "Điều 1: Quyết định tổ chức kỳ sát hạch"],
        ),
    ]

    nodes = build_canonical_nodes(revision_id="revision-1", drafts=drafts, parser_confidence=1.0)

    assert [node.label for node in nodes if node.node_type == "article"] == [
        "Dieu 43",
        "Dieu 40",
        "Dieu 41",
    ]
    appendix_nodes = [node for node in nodes if node.node_type == "appendix"]
    assert len(appendix_nodes) == 2
    assert all(node.structured_content["review_only"] is True for node in appendix_nodes)
    assert all(node.structured_content["answerable"] is False for node in appendix_nodes)
