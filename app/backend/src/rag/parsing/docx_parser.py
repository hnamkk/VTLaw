"""DOCX parser (preferred format for MVP, spec 10 §6).

python-docx preserves the document DOM, so table rows stay attached to their
headers — critical for the multi-page penalty tables. We walk the body in
document order, emitting paragraphs as text/heading blocks and tables as a
single ``table`` block each (rows flattened with a separator the chunker keeps
intact).
"""

from __future__ import annotations

import re

from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.rag.parsing.base import BlockKind, ParsedBlock, ParseResult, clean_extracted_text

# A paragraph whose text matches a legal heading marker is tagged as a heading so
# the chunker's structure detector can trust it even when Word styling is absent.
_HEADING_RE = re.compile(
    r"^\s*(chương|mục|điều)\s+[\dIVXLC]+",
    re.IGNORECASE,
)


def _iter_block_items(parent: _Document):
    """Yield paragraphs and tables in document order.

    python-docx exposes ``paragraphs`` and ``tables`` separately, losing their
    interleaving. Walking the body XML restores the real order so a penalty
    table stays next to the Điều/Khoản that introduces it.
    """
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _clean(text: str) -> str:
    return clean_extracted_text(text)


def _table_to_text(table: Table) -> str:
    """Flatten a table to text, one row per line, cells joined by ' | '.

    Keeps every row attached to the same block so the chunker never splits a
    penalty row away from its column headers (spec 10 §6).
    """
    lines: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            value = _clean(cell.text)
            # python-docx repeats merged-cell text for every covered grid cell.
            if value and (not cells or cells[-1] != value):
                cells.append(value)
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def parse_docx(path: str) -> ParseResult:
    document = Document(path)
    blocks: list[ParsedBlock] = []

    for item in _iter_block_items(document):
        if isinstance(item, Paragraph):
            text = _clean(item.text)
            if not text:
                continue
            kind = BlockKind.heading if _HEADING_RE.match(text) else BlockKind.text
            blocks.append(ParsedBlock(text=text, kind=kind))
        else:  # Table
            text = _table_to_text(item)
            if text:
                blocks.append(ParsedBlock(text=text, kind=BlockKind.table))

    result = ParseResult(blocks=blocks, confidence=1.0)
    if not blocks:
        result.warnings.append("DOCX rỗng hoặc không trích xuất được nội dung.")
        result.confidence = 0.0
    return result
