"""Structure-aware chunking for QCVN technical regulations."""

from __future__ import annotations

import re

from src.core.config import settings
from src.rag.chunking.base import (
    CHUNK_TYPE_FIGURE_CAPTION,
    CHUNK_TYPE_SIGN_DEFINITION,
    CHUNK_TYPE_SIGN_GROUP,
    CHUNK_TYPE_TABLE,
    CHUNK_TYPE_TECHNICAL_SECTION,
    ChunkDraft,
    DocMeta,
)
from src.rag.parsing.base import BlockKind, ParseResult

_PART_RE = re.compile(r"^\s*PHẦN\s+([IVXLCDM\d]+)\b[:.]?\s*(.*)$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,4})[.)]?\s+(.+)$")
_SIGN_RE = re.compile(r"\b([PWRIS]\s*[.-]?\s*\d{2,3}[a-z]?)\b", re.IGNORECASE)
_FIGURE_RE = re.compile(r"^\s*HÌNH\s+([A-Z]?\d+(?:\.\d+)*)\b[:.]?\s*(.*)$", re.IGNORECASE)
_SIGN_GROUP_WORDS = ("biển báo cấm", "biển hiệu lệnh", "biển nguy hiểm", "biển chỉ dẫn")
_LOCATOR_LABEL_MAX_LEN = 180


def normalize_sign_code(value: str) -> str:
    compact = re.sub(r"[\s-]+", ".", value.strip().upper())
    compact = re.sub(r"\.{2,}", ".", compact)
    if "." not in compact and len(compact) > 1:
        compact = f"{compact[0]}.{compact[1:]}"
    return re.sub(r"([A-Z])$", lambda match: match.group(1).lower(), compact)


def _split_text(text: str) -> list[str]:
    if len(text) <= settings.CHUNK_MAX_LEN:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in (part.strip() for part in text.splitlines() if part.strip()):
        if current and len(current) + len(paragraph) + 1 > settings.CHUNK_MAX_LEN:
            parts.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        parts.append(current)
    return parts


def _truncate_locator_label(value: str, max_len: int = _LOCATOR_LABEL_MAX_LEN) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip(" ,;") + "…"


def _format_sign_locator_label(sign_codes: list[str]) -> str:
    if not sign_codes:
        return ""
    prefix = f"Biển {len(sign_codes)} mã: " if len(sign_codes) > 1 else "Biển "
    selected: list[str] = []
    for code in sign_codes:
        candidate = prefix + ", ".join([*selected, code])
        suffix = "…" if len(selected) + 1 < len(sign_codes) else ""
        if len(candidate) + len(suffix) > _LOCATOR_LABEL_MAX_LEN:
            break
        selected.append(code)
    if not selected:
        return _truncate_locator_label(prefix + sign_codes[0])
    label = prefix + ", ".join(selected)
    if len(selected) < len(sign_codes):
        label += "…"
    return label


def chunk_qcvn(parsed: ParseResult, meta: DocMeta) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    part_label = ""
    section_number = ""
    section_title = ""
    buffer: list[str] = []
    content_kind = "technical_section"
    figure_ids: list[str] = []

    def flush() -> None:
        nonlocal buffer, content_kind, figure_ids
        body = "\n".join(buffer).strip()
        if not body:
            return
        sign_codes = sorted({normalize_sign_code(code) for code in _SIGN_RE.findall(body)})
        kind = CHUNK_TYPE_SIGN_DEFINITION if sign_codes else CHUNK_TYPE_TECHNICAL_SECTION
        if content_kind == "sign_group":
            kind = CHUNK_TYPE_SIGN_GROUP
        elif content_kind == "figure_caption":
            kind = CHUNK_TYPE_FIGURE_CAPTION
        locator_label = _truncate_locator_label(
            _format_sign_locator_label(sign_codes)
            if sign_codes
            else f"Mục {section_number}" if section_number else part_label or "Quy chuẩn"
        )
        path = [value for value in (part_label, f"{section_number} {section_title}".strip()) if value]
        for piece in _split_text(body):
            draft = ChunkDraft(
                text_content=piece,
                chunk_type=kind,
                display_path=" → ".join([meta.title, *path, locator_label]),
                heading_path=path,
                content_kind=content_kind,
                canonical_provision_id=(
                    f"{meta.document_number or meta.title}:{section_number or locator_label}"
                ),
                locator_type="sign_code" if sign_codes else "section",
                locator_label=locator_label,
                section_path=path,
                section_number=section_number or None,
                sign_codes=sign_codes,
                figure_ids=list(figure_ids),
            )
            draft.embedding_content = _embedding_content(meta, path, piece)
            drafts.append(draft)
        buffer = []
        content_kind = "technical_section"
        figure_ids = []

    for block in parsed.blocks:
        if block.kind is BlockKind.table:
            flush()
            path = [value for value in (part_label, section_title) if value]
            draft = ChunkDraft(
                text_content=block.text,
                chunk_type=CHUNK_TYPE_TABLE,
                display_path=" → ".join(
                    [value for value in (meta.title, part_label, f"Mục {section_number}") if value]
                ),
                heading_path=path,
                source_page=block.page,
                content_kind="table",
                locator_type="table",
                locator_label=f"Bảng tại mục {section_number}" if section_number else "Bảng",
                section_path=path,
                section_number=section_number or None,
            )
            draft.embedding_content = _embedding_content(meta, path, block.text)
            drafts.append(draft)
            continue

        for line in (value.strip() for value in block.text.splitlines() if value.strip()):
            part_match = _PART_RE.match(line)
            if part_match:
                flush()
                part_label = f"Phần {part_match.group(1)} {part_match.group(2)}".strip()
                section_number = ""
                section_title = ""
                continue
            section_match = _SECTION_RE.match(line)
            if section_match:
                flush()
                section_number = section_match.group(1)
                section_title = section_match.group(2).strip()
                content_kind = (
                    "sign_group"
                    if any(word in section_title.lower() for word in _SIGN_GROUP_WORDS)
                    else "technical_section"
                )
                buffer.append(line)
                continue
            figure_match = _FIGURE_RE.match(line)
            if figure_match:
                flush()
                figure_ids = [figure_match.group(1)]
                content_kind = "figure_caption"
                buffer.append(line)
                continue
            buffer.append(line)

    flush()
    for source_order, draft in enumerate(drafts):
        draft.source_order = source_order
    return drafts


def _embedding_content(meta: DocMeta, path: list[str], body: str) -> str:
    header = " | ".join(
        value
        for value in (
            meta.document_number,
            meta.title,
            meta.doc_type,
            meta.corpus,
            meta.effective_date,
            meta.status,
        )
        if value
    )
    return "\n".join([header, *path, body])[: settings.EMBEDDING_CONTENT_MAX_LEN]
