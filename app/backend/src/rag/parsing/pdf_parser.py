"""PDF parser (best-effort fallback, spec 10 §6).

pdfplumber loses table column headers across page breaks, so PDF is best-effort:
ADMIN is advised to upload DOCX. We extract text per page, strip repeated
header/footer lines (detected by frequency across pages), tag legal headings,
and derive a confidence score from how much extractable text we recovered.
"""

from __future__ import annotations

import re
from collections import Counter

import pdfplumber

from src.rag.parsing.base import (
    PARSER_WARNING_THRESHOLD,
    BlockKind,
    ParsedBlock,
    ParseResult,
    clean_extracted_text,
)

_HEADING_RE = re.compile(r"^\s*(chương|mục|điều)\s+[\dIVXLC]+", re.IGNORECASE)


def _clean(text: str) -> str:
    return clean_extracted_text(text)


def _detect_repeated_lines(pages_lines: list[list[str]]) -> set[str]:
    """Lines appearing on most pages are headers/footers, not content.

    A line repeated on >= 60% of pages (when there are 3+ pages) is treated as
    boilerplate and dropped from ``text_content`` per spec 10 §6.
    """
    if len(pages_lines) < 3:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages_lines:
        for line in set(lines):  # count once per page
            counts[line] += 1
    threshold = 0.6 * len(pages_lines)
    return {line for line, n in counts.items() if n >= threshold and len(line) < 120}


def parse_pdf(path: str) -> ParseResult:
    pages_lines: list[list[str]] = []
    char_pages = 0

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            raw = page.extract_text() or ""
            if raw.strip():
                char_pages += 1
            lines = [_clean(line) for line in raw.splitlines()]
            pages_lines.append([line for line in lines if line])

    boilerplate = _detect_repeated_lines(pages_lines)

    blocks: list[ParsedBlock] = []
    for page_idx, lines in enumerate(pages_lines, start=1):
        for line in lines:
            if line in boilerplate:
                continue
            kind = BlockKind.heading if _HEADING_RE.match(line) else BlockKind.text
            blocks.append(ParsedBlock(text=line, kind=kind, page=page_idx))

    result = ParseResult(blocks=blocks)
    # Confidence = fraction of pages that yielded extractable text. A scanned PDF
    # with no text layer scores ~0 and trips the ADMIN-review warning.
    result.confidence = (char_pages / page_count) if page_count else 0.0
    if not blocks:
        result.warnings.append("PDF rỗng hoặc không có lớp văn bản (có thể là bản scan).")
    if result.confidence < PARSER_WARNING_THRESHOLD:
        result.warnings.append(
            f"Độ tin cậy trích xuất thấp ({result.confidence:.0%}); "
            "ADMIN cần kiểm tra thủ công. Khuyến nghị upload bản DOCX."
        )
    return result
