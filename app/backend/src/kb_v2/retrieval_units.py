from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from uuid import uuid4

from src.core.config import settings
from src.models.kb_v2 import (
    KbV2CanonicalNode,
    KbV2DocumentRevision,
    KbV2LegalDocument,
    KbV2RetrievalUnit,
)
from src.rag.embedding import embed_texts

RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION = {
    "appendix",
    "form",
    "image_caption",
    "table",
}
CITATION_LABEL_MAX_LENGTH = 255
_ARTICLE_CITATION_RE = re.compile(r"(?:Điều|Dieu)\s+([0-9]+[A-Za-z]?)", re.IGNORECASE)
_CLAUSE_CITATION_RE = re.compile(r"(?:khoản|Khoản|Khoan)\s+([0-9]+[A-Za-z]?)", re.IGNORECASE)
_POINT_CITATION_RE = re.compile(r"(?:điểm|Điểm|Diem)\s+([A-Za-zĐđ])", re.IGNORECASE)


@dataclass
class GeneratedRetrievalUnits:
    units: list[KbV2RetrievalUnit]
    answerable_count: int


async def build_retrieval_units(
    *,
    document: KbV2LegalDocument,
    revision: KbV2DocumentRevision,
) -> GeneratedRetrievalUnits:
    approved_nodes = sorted(
        [
            node
            for node in revision.canonical_nodes
            if node.review_status == "approved"
            and not bool((node.structured_content or {}).get("structural_only"))
        ],
        key=lambda node: node.order_index,
    )
    if not approved_nodes:
        return GeneratedRetrievalUnits(units=[], answerable_count=0)

    parent_map = {node.node_id: node for node in revision.canonical_nodes}
    unit_specs: list[tuple[KbV2CanonicalNode, str, bool, str]] = []
    for node in approved_nodes:
        citation_label = citation_label_for_node(node=node, parent_map=parent_map)
        answerable = node_is_answerable(node)
        text = _embedding_text(
            document=document,
            node=node,
            citation_label=citation_label,
        )
        unit_specs.append((node, citation_label, answerable, text))

    answerable_texts = [text for _, _, answerable, text in unit_specs if answerable]
    vectors = await embed_texts(answerable_texts) if answerable_texts else []
    vector_iter = iter(vectors)

    units: list[KbV2RetrievalUnit] = []
    for node, citation_label, answerable, text in unit_specs:
        vector = next(vector_iter) if answerable else None
        answerable_status = _answerable_status(document=document) if answerable else "not_answerable"
        units.append(
            KbV2RetrievalUnit(
                retrieval_unit_id=str(uuid4()),
                canonical_node_id=node.node_id,
                document_id=document.document_id,
                revision_id=revision.revision_id,
                text=text,
                embedding_vector=vector,
                effective_from=document.effective_date,
                effective_to=document.expiry_date,
                answerable_status=answerable_status,
                citation_label=citation_label,
                content_hash=_content_hash(
                    document=document,
                    node=node,
                    citation_label=citation_label,
                    text=text,
                ),
                embedding_model=settings.EMBEDDING_MODEL_NAME if answerable else None,
                embedding_version="kb_v2_v1" if answerable else None,
                index_version="kb_v2_v1",
                metadata_json={
                    "node_type": node.node_type,
                    "label": node.label,
                    "order_index": node.order_index,
                    "answerable": answerable,
                },
            )
        )
    return GeneratedRetrievalUnits(
        units=units,
        answerable_count=sum(1 for _, _, answerable, _ in unit_specs if answerable),
    )


def citation_label_for_node(
    *,
    node: KbV2CanonicalNode,
    parent_map: dict[str, KbV2CanonicalNode] | None = None,
) -> str:
    structured_label = _structured_citation_label(node)
    if structured_label:
        return _fit_citation_label(structured_label, node=node)
    if parent_map is None:
        parent_map = {}
    return _fit_citation_label(_fallback_citation_label(node=node, parent_map=parent_map), node=node)


def _structured_citation_label(node: KbV2CanonicalNode) -> str | None:
    structured = node.structured_content or {}
    parts: list[str] = []
    chapter_num = _locator_value(structured.get("chapter_num"))
    article_num = _locator_value(structured.get("article_num"))
    clause_num = _locator_value(structured.get("clause_num"))
    point_num = _locator_value(structured.get("point_num"))

    if chapter_num and article_num:
        parts.append(f"Chương {chapter_num}")
    if article_num:
        parts.append(f"Điều {article_num}")
    if clause_num:
        parts.append(f"khoản {clause_num}")
    if point_num:
        parts.append(f"điểm {point_num}")
    if parts:
        return " > ".join(parts)
    if chapter_num:
        return f"Chương {chapter_num}"
    return None


def _locator_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fallback_citation_label(*, node: KbV2CanonicalNode, parent_map: dict[str, KbV2CanonicalNode]) -> str:
    labels: list[str] = []
    cursor = node
    seen: set[str] = set()
    while cursor is not None and cursor.node_id not in seen:
        seen.add(cursor.node_id)
        if cursor.label:
            labels.append(cursor.label.strip())
        cursor = parent_map.get(cursor.parent_id or "")
    labels.reverse()
    return " > ".join(label for label in labels if label) or f"Node {node.order_index}"


def _fit_citation_label(label: str, *, node: KbV2CanonicalNode) -> str:
    if len(label) <= CITATION_LABEL_MAX_LENGTH:
        return label
    leaf = (node.label or "").strip() or f"Node {node.order_index}"
    fallback = f"{leaf} > Node {node.order_index}"
    if len(fallback) <= CITATION_LABEL_MAX_LENGTH:
        return fallback
    suffix = f"... > Node {node.order_index}"
    prefix_length = max(1, CITATION_LABEL_MAX_LENGTH - len(suffix))
    return f"{leaf[:prefix_length].rstrip()}{suffix}"


def citation_mismatches_for_nodes(
    nodes: list[KbV2CanonicalNode],
) -> list[str]:
    parent_map = {node.node_id: node for node in nodes}
    mismatches: list[str] = []
    for node in sorted(nodes, key=lambda item: item.order_index):
        if node.review_status != "approved" or not node_is_answerable(node):
            continue
        citation_label = citation_label_for_node(node=node, parent_map=parent_map)
        structured = node.structured_content or {}
        mismatch = _citation_mismatch(node=node, citation_label=citation_label, structured=structured)
        if mismatch:
            mismatches.append(mismatch)
    return mismatches


def citation_mismatch_for_unit(
    *,
    node: KbV2CanonicalNode,
    citation_label: str | None,
) -> str | None:
    if not node_is_answerable(node):
        return None
    return _citation_mismatch(
        node=node,
        citation_label=citation_label or "",
        structured=node.structured_content or {},
    )


def _citation_mismatch(
    *,
    node: KbV2CanonicalNode,
    citation_label: str,
    structured: dict,
) -> str | None:
    article_num = _locator_value(structured.get("article_num"))
    clause_num = _locator_value(structured.get("clause_num"))
    point_num = _locator_value(structured.get("point_num"))
    if article_num and _last_match(_ARTICLE_CITATION_RE, citation_label) != article_num:
        return _citation_mismatch_message(node=node, expected=f"Điều {article_num}", actual=citation_label)
    if clause_num and _last_match(_CLAUSE_CITATION_RE, citation_label) != clause_num:
        return _citation_mismatch_message(node=node, expected=f"khoản {clause_num}", actual=citation_label)
    if point_num and (_last_match(_POINT_CITATION_RE, citation_label) or "").lower() != point_num.lower():
        return _citation_mismatch_message(node=node, expected=f"điểm {point_num}", actual=citation_label)
    return None


def _last_match(pattern: re.Pattern[str], value: str) -> str | None:
    matches = pattern.findall(value or "")
    return str(matches[-1]) if matches else None


def _citation_mismatch_message(*, node: KbV2CanonicalNode, expected: str, actual: str) -> str:
    label = node.label or f"Node {node.order_index}"
    return f"Mục {label} có trích dẫn chưa khớp: cần {expected}, hiện là {actual or 'chưa có'}."


def node_is_answerable(node: KbV2CanonicalNode) -> bool:
    if not (node.text or "").strip():
        return False
    structured = node.structured_content or {}
    if bool(structured.get("review_only")):
        return False
    if structured.get("answerable") is False:
        return False
    if node.node_type in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION:
        return bool(structured.get("answerable") is True)
    return True


def _embedding_text(
    *,
    document: KbV2LegalDocument,
    node: KbV2CanonicalNode,
    citation_label: str,
) -> str:
    parts = [
        f"Tieu de: {document.title or 'Khong ro'}",
        f"Loai van ban: {document.document_type or 'Khong ro'}",
        f"Co quan ban hanh: {document.issuing_authority or 'Khong ro'}",
        f"Hieu luc tu: {_fmt_date(document.effective_date)}",
        f"Trich dan: {citation_label}",
        f"Noi dung: {(node.text or '').strip()}",
    ]
    return "\n".join(parts).strip()


def _answerable_status(*, document: KbV2LegalDocument) -> str:
    today = date.today()
    if document.effective_date and document.effective_date > today:
        return "future"
    if document.expiry_date and document.expiry_date < today:
        return "historical"
    if document.legal_status == "suspended":
        return "suspended"
    return "active"


def _content_hash(
    *,
    document: KbV2LegalDocument,
    node: KbV2CanonicalNode,
    citation_label: str,
    text: str,
) -> str:
    payload = "||".join([document.document_id, node.node_id, citation_label, text]).encode("utf-8")
    return sha256(payload).hexdigest()


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "Khong ro"
