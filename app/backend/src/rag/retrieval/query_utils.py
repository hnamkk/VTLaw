"""Query normalization helpers shared by the current KB runtime."""

from __future__ import annotations

import re
import unicodedata

from src.rag.query_policy import get_query_policy

_LEGAL_DOC_KEYWORDS = (
    "thong tu",
    "nghi dinh",
    "quyet dinh",
    "luat",
    "bo luat",
    "quy chuan",
    "qcvn",
    "van ban hop nhat",
    "vbhn",
)
_LEGAL_DOC_ABBREVIATION_PATTERN = re.compile(r"\b(?:tt|nd|qd|qh)\b", re.IGNORECASE)
_SHORT_DOC_NUMBER_PATTERN = re.compile(r"\b\d{1,3}/\d{4}\b")
_SHORT_QCVN_NUMBER_PATTERN = re.compile(r"\b\d+:\d{4}/[A-ZĐ]+\b", re.IGNORECASE)
_EXPLICIT_DOC_LOOKUP_PATTERN = re.compile(
    r"\b(?:\d{1,3}/(?:\d{4}/(?:QH\d+|NĐ-CP|ND-CP|TT-[A-ZĐ]+|QĐ-[A-ZĐ]+|QD-[A-ZĐ]+)|VBHN-[A-ZĐ]+)|QCVN\s*\d+:\d{4}/[A-ZĐ]+)\b",
    re.IGNORECASE,
)
_SEMANTIC_DOC_REFERENCE_PATTERN = re.compile(
    r"\b(?:(?:nghi\s+dinh|luat|thong\s+tu|nd|nđ|tt)\s+)?"
    r"\d{1,3}/\d{4}(?:/(?:qh\d+|nđ-cp|nd-cp|tt-[a-zđ]+))?\b",
    re.IGNORECASE,
)
_ROAD_LAW_SCOPE_PHRASES = (
    "luat duong bo",
    "ket cau ha tang duong bo",
    "ha tang duong bo",
    "quan ly duong bo",
    "van tai duong bo",
)
_TRAFFIC_SAFETY_SCOPE_PHRASES = (
    "luat trat tu an toan giao thong duong bo",
    "luat trat tu",
    "an toan giao thong duong bo",
    "quy tac giao thong duong bo",
    "nguoi va phuong tien tham gia giao thong",
    "giai quyet tai nan giao thong",
)
_TOPIC_DOCUMENT_SCOPE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "16/2021/TT-BGTVT",
        (
            "giay chung nhan kiem dinh",
            "tem kiem dinh",
            "kiem dinh xe",
            "kiem dinh xe co gioi",
            "kiem dinh an toan ky thuat",
            "kiem dinh an toan ky thuat va bao ve moi truong",
        ),
    ),
    (
        "108/2026/TT-BCA",
        (
            "4 bai thuc hanh sat hach",
            "bon bai thuc hanh sat hach",
            "bai thuc hanh co ban",
            "thuc hanh co ban",
            "nguoi sat hach giay phep lai xe hang a1",
            "giay phep lai o to con hieu luc",
            "thi a1",
            "sat hach ly thuyet lai xe",
            "phan ly thuyet",
            "ly thuyet lai xe",
            "sat hach mo to hang a1",
            "sat hach moto hang a1",
            "mien sat hach ly thuyet a1",
        ),
    ),
    (
        "36/2024/TT-BYT",
        (
            "suc khoe nguoi lai xe",
            "nhom suc khoe 1",
            "tieu chuan suc khoe",
            "kham suc khoe nguoi lai xe",
        ),
    ),
    (
        "79/2024/TT-BCA",
        (
            "dang ky xe",
            "ho so dang ky xe",
            "ng k xe",
            "noi chu xe nop ho so",
            "noi nop ho so dang ky xe",
            "n p h s ng k xe",
            "nguon goc hop phap",
            "cap bien so xe",
        ),
    ),
    (
        "158/2024/ND-CP",
        (
            "kinh doanh van tai bang xe o to",
            "dieu kien kinh doanh van tai",
            "hoat dong van tai duong bo",
            "ben xe khach",
            "ben xe hang",
            "xe hang khac xe khach",
            "xe khach khac xe hang",
            "giay phep trong kinh doanh van tai",
            "nghi dinh ve kinh doanh van tai",
            "phu hieu va giay phep",
            "van tai duong bo quoc te",
        ),
    ),
)


def normalize_for_lookup(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_punct = re.sub(r"[^a-z0-9\s]", " ", without_marks)
    return re.sub(r"\s+", " ", without_punct).strip()


def is_explicit_document_lookup(query: str) -> bool:
    if _EXPLICIT_DOC_LOOKUP_PATTERN.search(query):
        return True
    normalized = normalize_for_lookup(query)
    if not normalized:
        return False
    has_doc_keyword = any(keyword in normalized for keyword in _LEGAL_DOC_KEYWORDS)
    has_doc_abbreviation = bool(_LEGAL_DOC_ABBREVIATION_PATTERN.search(normalized))
    has_short_number = bool(
        _SHORT_DOC_NUMBER_PATTERN.search(query.lower()) or _SHORT_QCVN_NUMBER_PATTERN.search(query)
    )
    return (has_doc_keyword or has_doc_abbreviation) and has_short_number


def semantic_document_scope_numbers(query: str) -> tuple[str, ...]:
    """Scope well-known base-law questions to the correct kho văn bản document.

    Luật Đường bộ 2024 (35/2024/QH15) and Luật Trật tự, an toàn giao thông
    đường bộ 2024 (36/2024/QH15) are semantically close. These rules only fire
    on strong title/scope phrases to prevent vector search from drifting between
    the two base laws.
    """
    if is_explicit_document_lookup(query):
        return ()
    normalized = normalize_for_lookup(query)
    padded = f" {normalized} "

    def has_phrase(phrase: str) -> bool:
        return f" {phrase} " in padded

    if has_phrase("tong quan he thong quy dinh giao thong duong bo") or (
        has_phrase("he thong quy dinh giao thong duong bo") and has_phrase("vai tro")
    ):
        return ("36/2024/QH15", "158/2024/ND-CP")
    if has_phrase("duong cao toc") and any(
        has_phrase(phrase) for phrase in ("la gi", "duoc hieu", "khai niem", "dinh nghia")
    ):
        return ("35/2024/QH15",)
    if has_phrase("duong cao toc"):
        return ("36/2024/QH15",)
    if has_phrase("dang ky xe") and has_phrase("kiem dinh xe") and has_phrase("kinh doanh van tai"):
        return ("79/2024/TT-BCA", "16/2021/TT-BGTVT", "158/2024/ND-CP")
    if has_phrase("luat nen") and has_phrase("thu tuc dang ky"):
        return ("36/2024/QH15", "79/2024/TT-BCA")
    if has_phrase("tong quan he thong quy dinh van tai duong bo") or (
        has_phrase("he thong quy dinh van tai duong bo") and has_phrase("vai tro")
    ):
        return ("35/2024/QH15", "158/2024/ND-CP")

    if (
        has_phrase("dang ky xe")
        and has_phrase("kinh doanh van tai")
        and any(has_phrase(phrase) for phrase in ("dieu kien", "chuan bi hoat dong", "phan biet"))
    ):
        return ("79/2024/TT-BCA", "158/2024/ND-CP")

    has_registration = has_phrase("dang ky xe")
    has_inspection = any(
        has_phrase(phrase)
        for phrase in (
            "kiem dinh xe",
            "kiem dinh xe co gioi",
            "kiem dinh an toan ky thuat",
            "giay chung nhan kiem dinh",
            "tem kiem dinh",
        )
    )

    if has_registration and has_inspection and has_phrase("kinh doanh van tai"):
        return ("79/2024/TT-BCA", "16/2021/TT-BGTVT", "158/2024/ND-CP")

    if has_registration and has_inspection:
        return ("79/2024/TT-BCA", "16/2021/TT-BGTVT")

    if (
        has_phrase("suc khoe nguoi lai")
        and any(has_phrase(phrase) for phrase in ("sat hach giay phep", "sat hach lai xe"))
    ):
        return ("36/2024/TT-BYT", "108/2026/TT-BCA")

    if (
        any(has_phrase(phrase) for phrase in ("toc do an toan", "toc do va khoang cach an toan"))
        and has_phrase("ha tang duong bo")
    ):
        return ("36/2024/QH15", "35/2024/QH15")

    topic_matches = [
        document_number
        for document_number, phrases in _TOPIC_DOCUMENT_SCOPE_RULES
        if any(has_phrase(phrase) for phrase in phrases)
    ]
    if len(set(topic_matches)) == 1:
        return (topic_matches[0],)

    road_law = any(has_phrase(phrase) for phrase in _ROAD_LAW_SCOPE_PHRASES)
    traffic_safety = any(has_phrase(phrase) for phrase in _TRAFFIC_SAFETY_SCOPE_PHRASES)
    if road_law and traffic_safety and any(
        has_phrase(phrase)
        for phrase in (
            "khac nhau",
            "pham vi trong tam",
            "trong tam nao",
            "so sanh",
        )
    ):
        return ("35/2024/QH15", "36/2024/QH15")
    if "hanh lang an toan duong bo" in padded:
        return ("35/2024/QH15",)
    if "doan duong qua khu dong dan cu" in padded:
        return ("36/2024/QH15",)
    if any(
        has_phrase(phrase)
        for phrase in (
            "giai quyet tai nan giao thong",
            "gi i quy t tai n n giao th ng",
            "khoang cach an toan",
            "khu dong dan cu",
            "phuong tien giao thong duong bo",
            "toc do va khoang cach an toan",
        )
    ):
        return ("36/2024/QH15",)
    if road_law and not traffic_safety:
        return ("35/2024/QH15",)
    if traffic_safety and not road_law:
        return ("36/2024/QH15",)
    return ()


def expand_query_for_retrieval(query: str) -> str:
    """Add deterministic, versioned retrieval hints for underspecified queries."""
    policy = get_query_policy().retrieval_expansion
    normalized = normalize_for_lookup(query)
    if not normalized:
        return query

    def contains_any_group(group_name: str) -> bool:
        return any(term in normalized for term in policy.term_groups[group_name])

    def contains_all_group(group_name: str) -> bool:
        return all(term in normalized for term in policy.term_groups[group_name])

    expansions: list[str] = []
    for rule in policy.rules:
        matched = False
        if rule.match_any and any(phrase in normalized for phrase in rule.match_any):
            matched = True
        if rule.match_any_group and contains_any_group(rule.match_any_group):
            matched = True
        if rule.match_all_group and contains_all_group(rule.match_all_group):
            matched = True
        if rule.requires_any_of:
            has_any_of = any(contains_any_group(group_name) for group_name in rule.requires_any_of)
            has_all_groups = all(
                any(contains_any_group(group_name) for group_name in group_expr.split("|"))
                for group_expr in rule.requires_all_groups
            )
            matched = has_any_of and has_all_groups
        if matched:
            expansions.append(rule.expansion_text)
    if expansions:
        return f"{query} " + " ".join(expansions)
    return query


def query_for_local_ranking(query: str) -> str:
    """Drop a cited document number when substantive question text remains."""
    stripped = _SEMANTIC_DOC_REFERENCE_PATTERN.sub(" ", query)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped if len(normalize_for_lookup(stripped).split()) >= 3 else query


__all__ = [
    "expand_query_for_retrieval",
    "is_explicit_document_lookup",
    "normalize_for_lookup",
    "query_for_local_ranking",
    "semantic_document_scope_numbers",
]
