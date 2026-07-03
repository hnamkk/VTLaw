"""Tests for parser helpers that need no real PDF/DOCX file (spec 10 §6).

Full file-based parsing is covered by integration tests with sample documents;
here we lock the format-agnostic logic: header/footer stripping, dispatch.
"""

from __future__ import annotations

import pytest

from src.rag.parsing import parse_document
from src.rag.parsing.base import clean_extracted_text
from src.rag.parsing.pdf_parser import _detect_repeated_lines


def test_detect_repeated_lines_flags_boilerplate():
    pages = [
        ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Điều 1. Nội dung A", "trang 1"],
        ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Điều 2. Nội dung B", "trang 2"],
        ["CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Điều 3. Nội dung C", "trang 3"],
    ]
    repeated = _detect_repeated_lines(pages)
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" in repeated
    assert "Điều 1. Nội dung A" not in repeated


def test_detect_repeated_lines_noop_for_few_pages():
    # Under 3 pages we can't reliably tell boilerplate from content.
    pages = [["a", "b"], ["a", "c"]]
    assert _detect_repeated_lines(pages) == set()


def test_parse_document_rejects_unsupported_extension():
    with pytest.raises(ValueError, match="Định dạng không hỗ trợ"):
        parse_document("some/file.txt")


def test_clean_extracted_text_removes_invisible_chars_without_changing_vietnamese():
    raw = "CỘNG\u00a0HÒA\u200b XÃ HỘI  CHỦ NGHĨA VIỆT NAM \u00ad ;"
    assert clean_extracted_text(raw) == "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM;"
