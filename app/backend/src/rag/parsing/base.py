"""Shared types for document parsers.

A parser turns a raw PDF/DOCX file into an ordered list of ``ParsedBlock``s plus
a ``ParseResult`` carrying document-level warnings and a confidence score. The
hierarchical chunker (spec 10 §4) consumes these blocks; it never sees the raw
file. Keeping the block contract format-agnostic lets the DOCX and PDF parsers
diverge in extraction while feeding one chunker.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum


class BlockKind(str, Enum):
    """Coarse role of a block, assigned by the parser, refined by the chunker."""

    text = "text"
    heading = "heading"
    table = "table"


@dataclass
class ParsedBlock:
    """One logical unit of text extracted from the source document.

    ``text`` is cleaned (header/footer stripped); ``page`` is 1-based and may be
    None for DOCX where page boundaries are not reliable.
    """

    text: str
    kind: BlockKind = BlockKind.text
    page: int | None = None


@dataclass
class ParseResult:
    """Output of a parser run for a single source file."""

    blocks: list[ParsedBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Mean extraction confidence in [0, 1]. < PARSER_WARNING_THRESHOLD (0.90)
    # forces an ADMIN review warning per spec 10 §6/§7.
    confidence: float = 1.0


PARSER_WARNING_THRESHOLD = 0.90

_INVISIBLE_CHARS_RE = re.compile(r"[\u00ad\u200b-\u200d\u2060\ufeff]")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")


def clean_extracted_text(text: str) -> str:
    """Normalize extraction artifacts without rewriting legal wording."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\xa0", " ")
    normalized = _INVISIBLE_CHARS_RE.sub("", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", normalized)
    return normalized.strip()
