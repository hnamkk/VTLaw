from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from uuid import uuid4

from src.legal_kb.metadata import normalize_document_role, normalize_document_type
from src.models.legal_kb import (
    LegalKbNode,
    LegalKbRevision,
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbSummary,
)

_METADATA_FIELDS = (
    "title",
    "document_number",
    "document_type",
    "issuing_authority",
    "issued_date",
    "effective_date",
    "expiry_date",
    "document_role",
)
_SCOPE_PATTERNS = (
    re.compile(r"^(luat|nghi dinh|thong tu|quy che|quyet dinh|van ban) nay quy dinh ve\b"),
    re.compile(r"\bpham vi dieu chinh\b"),
    re.compile(r"\bdoi tuong ap dung\b"),
)
_BOILERPLATE_CHAPTER_PATTERNS = (
    re.compile(r"\bdieu khoan thi hanh\b"),
    re.compile(r"\bquy dinh chuyen tiep\b"),
)


def seed_initial_metadata_proposals(
    *,
    document: LegalKbDocument,
    revision: LegalKbRevision,
) -> list[LegalKbMetadataProposal]:
    values: dict[str, str] = {}
    for field_name in _METADATA_FIELDS:
        raw_value = _proposal_value_for_field(document=document, field_name=field_name)
        if raw_value:
            values[field_name] = raw_value

    proposals: list[LegalKbMetadataProposal] = []
    for field_name, proposed_value in values.items():
        proposals.append(
            LegalKbMetadataProposal(
                proposal_id=str(uuid4()),
                document_id=document.document_id,
                revision_id=revision.revision_id,
                field_name=field_name,
                proposed_value=proposed_value,
                source_type="upload",
                confidence=1.0,
                review_status="approved",
                provenance={"seeded_from": "upload_form", "approval_mode": "auto_on_upload"},
                reviewed_by=revision.uploaded_by,
                reviewed_at=revision.uploaded_at or datetime.now(tz=UTC),
            )
        )
    return proposals


def build_summary_proposal(
    *,
    document: LegalKbDocument,
    revision: LegalKbRevision,
    canonical_nodes: list[LegalKbNode],
) -> LegalKbSummary | None:
    content = _build_standard_summary_draft(document=document, canonical_nodes=canonical_nodes)
    if not content:
        return None

    return LegalKbSummary(
        summary_id=str(uuid4()),
        document_id=document.document_id,
        revision_id=revision.revision_id,
        content=content[:4000],
        review_status="needs_review",
    )


def infer_document_role(*, title: str | None, document_type: str | None, source_note: str | None) -> str:
    haystacks = [value.lower() for value in (title, document_type, source_note) if value]
    amendment_terms = (
        "sua doi",
        "bo sung",
        "thay the",
        "amend",
        "replace",
        "annul",
        "bai bo",
        "huong dan",
    )
    accent_terms = ("sua doi", "bo sung", "thay the", "bai bo", "huong dan")
    for haystack in haystacks:
        if any(term in haystack for term in amendment_terms) or any(
            term in haystack for term in accent_terms
        ):
            return "amendment"
    return "primary"


def _proposal_value_for_field(*, document: LegalKbDocument, field_name: str) -> str | None:
    if field_name == "document_role":
        uploaded_role = document.metadata_json.get("document_role")
        if isinstance(uploaded_role, str) and uploaded_role.strip():
            return normalize_document_role(uploaded_role)
        return infer_document_role(
            title=document.title,
            document_type=document.document_type,
            source_note=document.metadata_json.get("source_note"),
        )
    value = getattr(document, field_name)
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        if field_name == "document_type":
            return normalize_document_type(value)
        return value or None
    return str(value)


def _build_standard_summary_draft(
    *,
    document: LegalKbDocument,
    canonical_nodes: list[LegalKbNode],
) -> str:
    scope_text = _detect_scope_text(canonical_nodes)
    main_topics = _main_topic_summary(canonical_nodes)
    review_only_notes = _review_only_notes(canonical_nodes)
    risky_count = sum(
        1
        for node in canonical_nodes
        if node.node_type in {"appendix", "form", "image_caption", "table"}
        and not bool((node.structured_content or {}).get("review_only"))
    )

    lines = [
        "Tóm tắt chuẩn (bản nháp)",
        "",
        "Thông tin pháp lý",
        _legal_info_line(document),
        "",
        "Phạm vi / đối tượng áp dụng",
        scope_text or "Chưa tự xác định chắc chắn từ cấu trúc văn bản; admin cần bổ sung khi duyệt.",
        "",
        "Nội dung chính",
        main_topics or "Chưa tự động rút ra được nhóm nội dung chính; admin cần bổ sung ngắn gọn.",
        "",
        "Ghi chú kiểm tra",
        "- Summary chuẩn này chỉ tóm tắt nội dung nguyên bản của từng văn bản. Nội dung hiện hành sau sửa đổi được xử lý ở summary động hoặc view hợp nhất sau khi quan hệ pháp lý được duyệt.",
    ]

    if review_only_notes:
        lines.append(f"- Phát hiện nội dung đối chiếu/review-only: {review_only_notes}.")
    if risky_count:
        lines.append(
            f"- Còn {risky_count} node bảng/mẫu/phụ lục/ảnh cần admin quyết định answerable hoặc review-only trước khi publish."
        )

    return "\n".join(lines).strip()


def _legal_info_line(document: LegalKbDocument) -> str:
    parts = [
        document.title or "Văn bản chưa rõ tên",
        f"số {document.document_number}" if document.document_number else None,
        f"do {document.issuing_authority} ban hành" if document.issuing_authority else None,
        f"ngày {_fmt_date(document.issued_date)}" if document.issued_date else None,
        f"có hiệu lực từ {_fmt_date(document.effective_date)}" if document.effective_date else None,
    ]
    sentence = " ".join(part for part in parts if part)
    return sentence.strip().rstrip(".") + "."


def _detect_scope_text(canonical_nodes: list[LegalKbNode]) -> str | None:
    candidates = [
        node
        for node in canonical_nodes
        if node.node_type in {"section", "article", "clause"}
        and not bool((node.structured_content or {}).get("review_only"))
    ]
    for node in candidates[:20]:
        text = _clean_text(node.text)
        normalized = _normalize_text(text)
        if not text:
            continue
        if any(pattern.search(normalized) for pattern in _SCOPE_PATTERNS):
            return text[:400]
    return None


def _main_topic_summary(canonical_nodes: list[LegalKbNode]) -> str:
    chapters = [
        _chapter_topic(_clean_text(node.text))
        for node in canonical_nodes
        if node.node_type == "chapter" and _chapter_topic(_clean_text(node.text))
    ]
    if chapters:
        filtered = [topic for topic in chapters if not _is_boilerplate_chapter(topic)]
        selected = filtered[:4] or chapters[:3]
        compact = "; ".join(topic.lower() for topic in selected)
        if len(chapters) > len(selected):
            return (
                f"Văn bản gồm {len(chapters)} chương. Các nhóm nội dung chính tập trung vào: "
                f"{compact}; cùng các quy định thi hành và nội dung liên quan."
            )
        return f"Các nhóm nội dung chính tập trung vào: {compact}."

    article_snippets = [
        _clean_text(node.text)
        for node in canonical_nodes
        if node.node_type == "article"
        and not bool((node.structured_content or {}).get("review_only"))
        and _clean_text(node.text)
    ]
    if article_snippets:
        summary = "; ".join(text[:120].lower() for text in article_snippets[:3])
        return f"Các nội dung nổi bật gồm: {summary}."
    return ""


def _review_only_notes(canonical_nodes: list[LegalKbNode]) -> str:
    roles: list[str] = []
    for node in canonical_nodes:
        role = (node.structured_content or {}).get("review_only_role")
        if not isinstance(role, str):
            continue
        label = _role_label(role)
        if label not in roles:
            roles.append(label)
    return ", ".join(roles)


def _role_label(role: str) -> str:
    mapping = {
        "national_header": "quốc hiệu, tiêu ngữ",
        "issuance_block": "thông tin ban hành",
        "signature_block": "người ký / khối ký ban hành",
        "distribution_list": "nơi nhận",
    }
    return mapping.get(role, role)


def _chapter_topic(value: str) -> str:
    topic = value.split(" Mục ", 1)[0].strip()
    if len(topic) <= 180:
        return topic
    return topic[:177].rstrip(" ,;:.") + "..."


def _is_boilerplate_chapter(value: str) -> bool:
    normalized = _normalize_text(value)
    return any(pattern.search(normalized) for pattern in _BOILERPLATE_CHAPTER_PATTERNS)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().split())


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", _clean_text(value))
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.replace("Đ", "D").replace("đ", "d").lower()


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else "chưa rõ"
