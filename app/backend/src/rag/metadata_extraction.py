"""Conservative metadata candidates extracted for HITL review."""

from __future__ import annotations

import re
from datetime import date

_VI_DATE_RE = re.compile(
    r"co hieu luc(?: thi hanh)?(?: ke)? tu ngay\s+"
    r"(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})",
    re.IGNORECASE,
)
_NUMERIC_DATE_RE = re.compile(
    r"co hieu luc(?: thi hanh)?(?: ke)? tu ngay\s+"
    r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
    re.IGNORECASE,
)
_FALLBACK_VI_DATE_RE = re.compile(
    r"ke tu ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})",
    re.IGNORECASE,
)
_FALLBACK_NUMERIC_DATE_RE = re.compile(
    r"ke tu ngay\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
    re.IGNORECASE,
)
_EFFECTIVE_SECTION_RE = re.compile(
    r"\bdieu\s+\d+[.:]?\s+hieu luc thi hanh\b",
    re.IGNORECASE,
)
_TEXT_DOC_NUMBER_PATTERNS = (
    re.compile(r"luat so:\s*([0-9]{1,3}/[0-9]{4}/QH[0-9]+)", re.IGNORECASE),
    re.compile(r"so:\s*([0-9]{1,3}/[0-9]{4}/ND-CP)", re.IGNORECASE),
    re.compile(r"so:\s*([0-9]{1,3}/[0-9]{4}/TT-[A-Z-]+)", re.IGNORECASE),
    re.compile(r"so:\s*([0-9]{1,3}/[0-9]{4}/QD-[A-Z-]+)", re.IGNORECASE),
)
_FILENAME_DOC_NUMBER_RE = re.compile(
    r"(?P<number>\d{1,3})_(?P<year>\d{4})_(?P<token>QH\d+|ND-CP|TT-[A-Z-]+|QD-[A-Z-]+)",
    re.IGNORECASE,
)
_DOC_TYPE_LABELS = {
    "LUAT": "Luật",
    "BO_LUAT": "Bộ luật",
    "NGHI_DINH": "Nghị định",
    "THONG_TU": "Thông tư",
    "QUYET_DINH": "Quyết định",
    "CONG_VAN": "Công văn",
    "QUY_CHUAN": "QCVN",
}


def _normalize_ascii(text: str) -> str:
    replacements = {
        "đ": "d",
        "Đ": "D",
        "á": "a",
        "à": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "ă": "a",
        "ắ": "a",
        "ằ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ấ": "a",
        "ầ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "é": "e",
        "è": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ế": "e",
        "ề": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "í": "i",
        "ì": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ó": "o",
        "ò": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ô": "o",
        "ố": "o",
        "ồ": "o",
        "ổ": "o",
        "ỗ": "o",
        "ộ": "o",
        "ơ": "o",
        "ớ": "o",
        "ờ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ú": "u",
        "ù": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ứ": "u",
        "ừ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ý": "y",
        "ỳ": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
    }
    normalized = text
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def extract_effective_date_candidate(text: str) -> date | None:
    """Return a general effective date, preferring the formal effective section."""
    normalized = _normalize_ascii(text)
    section_matches = list(_EFFECTIVE_SECTION_RE.finditer(normalized))
    search_regions = []
    if section_matches:
        search_regions.append(normalized[section_matches[-1].start() : section_matches[-1].start() + 2000])
    search_regions.append(normalized)

    for region in search_regions:
        match = next(
            (candidate for pattern in (_VI_DATE_RE, _NUMERIC_DATE_RE) if (candidate := pattern.search(region))),
            None,
        )
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None
    for pattern in (_FALLBACK_VI_DATE_RE, _FALLBACK_NUMERIC_DATE_RE):
        match = pattern.search(normalized)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None
    return None


def extract_document_number_candidate(text: str) -> str | None:
    """Extract a legal document number from parsed text when present."""
    normalized = _normalize_ascii(text)
    for pattern in _TEXT_DOC_NUMBER_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return match.group(1).upper()
    return None


def infer_document_number_from_filename(filename: str) -> str | None:
    """Infer a conservative document number from upload/raw filenames."""
    match = _FILENAME_DOC_NUMBER_RE.search(filename.replace(".", "_"))
    if match is None:
        return None
    token = match.group("token").upper().replace("ND-CP", "NĐ-CP").replace("QD-", "QĐ-")
    return f"{int(match.group('number'))}/{match.group('year')}/{token}"


def build_canonical_title(doc_type: str, document_number: str | None, fallback_title: str) -> str:
    """Return a stable title that preserves the canonical document number when known."""
    if document_number:
        label = _DOC_TYPE_LABELS.get(doc_type, "Văn bản")
        return f"{label} {document_number}"
    return fallback_title


__all__ = [
    "build_canonical_title",
    "extract_document_number_candidate",
    "extract_effective_date_candidate",
    "infer_document_number_from_filename",
]
