"""Document parsing: route a source file to the right parser by extension.

DOCX is preferred (spec 10 §6); PDF is best-effort. The chunker consumes the
returned ``ParseResult`` regardless of source format.
"""

from __future__ import annotations

from pathlib import Path

from src.rag.parsing.base import (
    PARSER_WARNING_THRESHOLD,
    BlockKind,
    ParsedBlock,
    ParseResult,
)
from src.rag.parsing.docx_parser import parse_docx
from src.rag.parsing.pdf_parser import parse_pdf


def parse_document(path: str) -> ParseResult:
    """Parse a PDF or DOCX file into structured blocks.

    Raises ValueError for unsupported extensions so the ingestion service can
    surface a clear error to ADMIN rather than producing empty chunks.
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"Định dạng không hỗ trợ: {suffix!r}. Chỉ nhận .pdf hoặc .docx.")


__all__ = [
    "BlockKind",
    "ParsedBlock",
    "ParseResult",
    "PARSER_WARNING_THRESHOLD",
    "parse_document",
    "parse_docx",
    "parse_pdf",
]
