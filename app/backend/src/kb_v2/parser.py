"""KB v2 canonical-node parser for DOCX ingestion.

This layer reuses the existing DOCX parser + legal chunker, then adds KB v2
review semantics:
- normal legal text is auto-approved
- tables/forms inside article/clause/point are answerable
- appendix materials and footnote/editorial notes are review-only
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import uuid4

from src.models.kb_v2 import KbV2CanonicalNode
from src.rag.chunking import ChunkDraft, DocMeta, chunk_document
from src.rag.parsing import ParseResult, parse_document

_HEADER_TERMS = (
    "cong hoa xa hoi chu nghia viet nam",
    "doc lap - tu do - hanh phuc",
)
_SIGNATURE_TERMS = (
    "chu tich quoc hoi",
    "pho chu tich quoc hoi",
    "thu tuong",
    "pho thu tuong",
    "bo truong",
    "thu truong",
    "tm.",
    "kt.",
    "tl.",
    "tuq.",
)
_DISTRIBUTION_TERMS = ("noi nhan",)
_ISSUANCE_TERMS = (
    "luat so:",
    "nghi dinh so:",
    "thong tu so:",
    "quyet dinh so:",
    "ha noi, ngay",
)
_APPENDIX_HEADINGS = (
    "phu luc",
    "mau so",
    "bieu mau",
    "danh muc",
)
_FORM_HEADINGS = (
    re.compile(r"^mau\s+so\b"),
    re.compile(r"^bieu\s+mau\b"),
)
_FOOTNOTE_PATTERNS = (
    re.compile(r"^\[\d+\](?:\s+|[:.-])"),
    re.compile(r"^chu thich\s*[:\-]"),
    re.compile(r"^ghi chu\s*[:\-]"),
    re.compile(r"^nguon\s*[:\-]"),
)


@dataclass(frozen=True)
class KbV2ParseArtifacts:
    parsed: ParseResult
    drafts: list[ChunkDraft]


@dataclass
class _NodeContext:
    chapter_node_id: str | None = None
    chapter_label: str | None = None
    article_node_id: str | None = None
    article_label: str | None = None
    clause_node_id: str | None = None
    clause_label: str | None = None
    point_node_id: str | None = None
    point_label: str | None = None
    appendix_node_id: str | None = None
    appendix_label: str | None = None
    in_appendix: bool = False


def parse_docx_into_artifacts(*, source_path: str, title: str) -> KbV2ParseArtifacts:
    parsed = parse_document(source_path)
    meta = DocMeta(
        title=title,
        doc_type="KB_DRAFT",
        effective_date="draft",
        status="draft",
        parser_profile="kb_v2",
        parser_version="kb-v2-p1",
    )
    drafts = chunk_document(parsed, meta)
    return KbV2ParseArtifacts(parsed=parsed, drafts=drafts)


def build_canonical_nodes(
    *,
    revision_id: str,
    drafts: list[ChunkDraft],
    parser_confidence: float,
) -> list[KbV2CanonicalNode]:
    nodes: list[KbV2CanonicalNode] = []
    context = _NodeContext()

    for order_index, draft in enumerate(_restore_structural_article_drafts(drafts)):
        node_type = _map_node_type(draft, context=context)
        parent_id = _resolve_parent_id(node_type=node_type, context=context)
        container_type, container_label = _container_metadata(draft=draft, context=context)

        node = KbV2CanonicalNode(
            node_id=str(uuid4()),
            revision_id=revision_id,
            parent_id=parent_id,
            node_type=node_type,
            label=_build_label(draft, node_type),
            text=draft.text_content,
            order_index=order_index,
            provenance={
                "source_order": draft.source_order,
                "source_page": draft.source_page,
                "display_path": draft.display_path,
                "heading_path": draft.heading_path,
                "parser_confidence": parser_confidence,
            },
            review_status="needs_review",
            structured_content={
                "chunk_type": draft.chunk_type,
                "content_kind": draft.content_kind,
                "article_num": draft.article_num,
                "clause_num": draft.clause_num,
                "point_num": draft.point_num,
                "chapter_num": draft.chapter_num,
                "locator_type": draft.locator_type,
                "locator_label": draft.locator_label,
                "section_path": draft.section_path,
                "section_number": draft.section_number,
                "table_id": draft.table_id,
                "container_type": container_type,
                "container_label": container_label,
                "in_appendix": context.in_appendix,
            },
        )
        _annotate_review_only_role(node=node, draft=draft)
        _annotate_answerability(node=node)
        nodes.append(node)
        _advance_context(context=context, node=node, draft=draft)

    return nodes


def _restore_structural_article_drafts(drafts: list[ChunkDraft]) -> list[ChunkDraft]:
    """Keep an article parent when the shared retrieval chunker drops its empty body."""
    restored: list[ChunkDraft] = []
    current_article_num: int | None = None
    in_appendix = False

    for draft in drafts:
        if (
            not in_appendix
            and draft.article_num is not None
            and draft.article_num != current_article_num
        ):
            if draft.chunk_type != "dieu":
                restored.append(_structural_article_draft(draft))
            current_article_num = draft.article_num

        restored.append(draft)
        if _is_appendix_heading(draft):
            in_appendix = True

    return restored


def _structural_article_draft(child: ChunkDraft) -> ChunkDraft:
    article_label = f"Điều {child.article_num}"
    article_heading = next(
        (
            heading
            for heading in reversed(child.heading_path)
            if heading.casefold().startswith(article_label.casefold())
        ),
        article_label,
    )
    _, separator, title = article_heading.partition(":")
    return ChunkDraft(
        text_content=title.strip() if separator and title.strip() else article_label,
        chunk_type="dieu",
        chapter_num=child.chapter_num,
        article_num=child.article_num,
        heading_path=list(child.heading_path),
        display_path=child.display_path,
        source_page=child.source_page,
        source_order=child.source_order,
        content_kind="structure",
    )


def _map_node_type(draft: ChunkDraft, *, context: _NodeContext) -> str:
    if draft.content_kind == "table":
        return "table"
    if context.in_appendix:
        if _is_form_heading(draft):
            return "form"
        return "appendix"
    if draft.chunk_type == "chuong":
        return "chapter"
    if draft.chunk_type == "dieu":
        return "article"
    if draft.chunk_type == "khoan":
        return "clause"
    if draft.chunk_type == "diem":
        return "point"
    if _is_form_heading(draft):
        return "form"
    if _is_appendix_heading(draft):
        return "appendix"
    if draft.content_kind == "preamble":
        return "section"
    return "appendix"


def _build_label(draft: ChunkDraft, node_type: str) -> str | None:
    if node_type == "chapter" and draft.chapter_num is not None:
        return f"Chuong {draft.chapter_num}"
    if node_type == "article" and draft.article_num is not None:
        return f"Dieu {draft.article_num}"
    if node_type == "clause" and draft.clause_num is not None:
        return f"Khoan {draft.clause_num}"
    if node_type == "point" and draft.point_num:
        return f"Diem {draft.point_num}"
    if node_type == "table":
        return "Bang"
    if node_type == "form":
        return "Bieu mau"
    if draft.display_path:
        tail = draft.display_path.split("→")[-1].strip()
        if tail:
            return tail
        tail = draft.display_path.split("->")[-1].strip()
        return tail or None
    return None


def _annotate_review_only_role(*, node: KbV2CanonicalNode, draft: ChunkDraft) -> None:
    role = _review_only_role(draft)
    if role is None:
        return
    structured_content = dict(node.structured_content or {})
    structured_content["review_only"] = True
    structured_content["review_only_role"] = role
    structured_content["answerable"] = False
    node.structured_content = structured_content
    node.label = _review_only_label(role)


def _annotate_answerability(*, node: KbV2CanonicalNode) -> None:
    structured_content = dict(node.structured_content or {})
    if structured_content.get("content_kind") == "structure":
        structured_content["structural_only"] = True
        structured_content["answerable"] = False
        node.structured_content = structured_content
        return
    if structured_content.get("review_only"):
        node.structured_content = structured_content
        return
    if node.node_type == "appendix":
        structured_content["review_only"] = True
        structured_content["review_only_role"] = "appendix_material"
        structured_content["answerable"] = False
        node.label = _review_only_label("appendix_material")
        node.structured_content = structured_content
        return
    if node.node_type in {"table", "form"}:
        if structured_content.get("in_appendix"):
            structured_content["review_only"] = True
            structured_content["review_only_role"] = "appendix_material"
            structured_content["answerable"] = False
            node.label = _review_only_label("appendix_material")
        else:
            structured_content["answerable"] = True
    node.structured_content = structured_content


def _review_only_role(draft: ChunkDraft) -> str | None:
    normalized = _normalize_text(draft.text_content)
    if not normalized:
        return None
    if _is_footnote_or_editorial_note(draft):
        return "citation_note"
    if any(term in normalized for term in _HEADER_TERMS):
        return "national_header"
    if any(term in normalized for term in _DISTRIBUTION_TERMS):
        return "distribution_list"
    if any(term in normalized for term in _SIGNATURE_TERMS):
        return "signature_block"
    if draft.content_kind in {"preamble", "table"} and any(
        term in normalized for term in _ISSUANCE_TERMS
    ):
        return "issuance_block"
    return None


def _review_only_label(role: str) -> str:
    if role == "national_header":
        return "Quoc hieu, tieu ngu"
    if role == "signature_block":
        return "Khoi ky ban hanh"
    if role == "distribution_list":
        return "Noi nhan"
    if role == "issuance_block":
        return "Thong tin ban hanh"
    if role == "appendix_material":
        return "Phu luc / bieu mau doi chieu"
    if role == "citation_note":
        return "Chu thich / trich dan cuoi trang"
    return "Noi dung doi chieu"


def _resolve_parent_id(*, node_type: str, context: _NodeContext) -> str | None:
    if node_type == "chapter":
        return None
    if node_type == "article":
        return context.chapter_node_id
    if node_type == "clause":
        return context.article_node_id
    if node_type == "point":
        return context.clause_node_id or context.article_node_id
    if context.in_appendix and context.appendix_node_id and node_type != "appendix":
        return context.appendix_node_id
    return context.point_node_id or context.clause_node_id or context.article_node_id or context.chapter_node_id


def _container_metadata(*, draft: ChunkDraft, context: _NodeContext) -> tuple[str | None, str | None]:
    if context.in_appendix:
        return "appendix", context.appendix_label
    if context.point_node_id:
        return "point", context.point_label
    if context.clause_node_id:
        return "clause", context.clause_label
    if context.article_node_id:
        return "article", context.article_label
    if context.chapter_node_id:
        return "chapter", context.chapter_label
    if draft.point_num:
        return "point", f"Diem {draft.point_num}"
    if draft.clause_num is not None:
        return "clause", f"Khoan {draft.clause_num}"
    if draft.article_num is not None:
        return "article", f"Dieu {draft.article_num}"
    if draft.chapter_num is not None:
        return "chapter", f"Chuong {draft.chapter_num}"
    return None, None


def _advance_context(*, context: _NodeContext, node: KbV2CanonicalNode, draft: ChunkDraft) -> None:
    if node.node_type == "chapter":
        context.chapter_node_id = node.node_id
        context.chapter_label = node.label
        context.article_node_id = None
        context.article_label = None
        context.clause_node_id = None
        context.clause_label = None
        context.point_node_id = None
        context.point_label = None
        return
    if node.node_type == "article":
        context.article_node_id = node.node_id
        context.article_label = node.label
        context.clause_node_id = None
        context.clause_label = None
        context.point_node_id = None
        context.point_label = None
        return
    if node.node_type == "clause":
        context.clause_node_id = node.node_id
        context.clause_label = node.label
        context.point_node_id = None
        context.point_label = None
        return
    if node.node_type == "point":
        context.point_node_id = node.node_id
        context.point_label = node.label
        return
    if _is_appendix_heading(draft):
        context.in_appendix = True
        context.appendix_node_id = node.node_id
        context.appendix_label = node.label
        context.point_node_id = None


def _is_appendix_heading(draft: ChunkDraft) -> bool:
    if draft.chunk_type != "phu_luc":
        return False
    normalized = _normalize_text(draft.text_content)
    if not normalized:
        return False
    return any(normalized.startswith(term) for term in _APPENDIX_HEADINGS)


def _is_form_heading(draft: ChunkDraft) -> bool:
    normalized = _normalize_text(draft.text_content)
    if not normalized:
        return False
    return any(pattern.match(normalized) for pattern in _FORM_HEADINGS)


def _is_footnote_or_editorial_note(draft: ChunkDraft) -> bool:
    normalized = _normalize_text(draft.text_content)
    if not normalized:
        return False
    return any(pattern.match(normalized) for pattern in _FOOTNOTE_PATTERNS)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("Đ", "D").replace("đ", "d").lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
