"""Scope classifier using embedding cosine similarity (spec 11 §3).

Non-LLM: compares query embedding against a set of reference vectors
representing in-scope topics (road transport, traffic law, vehicle
registration, fines, permits). Fast and deterministic.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np

from src.core.config import settings
from src.rag.embedding import embed_query
from src.schemas.rag import ScopeLabel, ScopeResult

_LEGAL_DOCUMENT_REFERENCE_PATTERN = re.compile(
    r"\b(?:\d{1,3}/\d{4}|"
    r"(?:nd|nđ|nghi\s+dinh|nghị\s+định|tt|thong\s+tu|thông\s+tư|"
    r"luat|luật|qh|qcvn)\s*\d{1,4})\b",
    re.IGNORECASE,
)

_REFERENCE_PHRASES: list[str] = [
    "quy định xử phạt vi phạm giao thông đường bộ",
    "giấy phép lái xe ô tô xe máy",
    "đăng ký xe cơ giới đăng kiểm phương tiện",
    "phù hiệu xe vận tải giấy phép kinh doanh vận tải",
    "mức phạt nồng độ cồn tốc độ",
    "biển báo giao thông quy tắc nhường đường",
    "tai nạn giao thông trách nhiệm bồi thường",
    "điều kiện kinh doanh vận tải hành khách hàng hóa",
    "niên hạn sử dụng xe ô tô xe tải",
    "bảo hiểm trách nhiệm dân sự chủ xe cơ giới",
    # Unaccented versions for unaccented queries in golden dataset
    "quy dinh xu phat vi pham giao thong duong bo",
    "giay phep lai xe o to xe may",
    "dang ky xe co gioi dang kiem phuong tien",
    "phu hieu xe van tai giay phep kinh doanh van tai",
    "muc phat nong do con toc do",
    "bien bao giao thong quy tac nhuong duong",
    "tai nan giao thong trach nhiem boi thuong",
    "dieu kien kinh doanh van tai hanh khach hang hoa",
    "nien han su dung xe o to xe tai",
    "bao hiem trach nhiem dan su chu xe co gioi",
    # Specific keywords and short phrases (accented & unaccented)
    "phạt",
    "phạt tiền",
    "mức phạt",
    "bị phạt",
    "phat",
    "phat tien",
    "muc phat",
    "bi phat",
    "giấy phép",
    "phù hiệu",
    "đăng kiểm",
    "biển số",
    "giay phep",
    "phu hieu",
    "dang kiem",
    "bien so",
    "giấy phép lái xe",
    "bằng lái xe",
    "bằng lái",
    "giay phep lai xe",
    "bang lai xe",
    "bang lai",
    "xe tải",
    "xe khách",
    "xe máy",
    "ô tô",
    "tai xế",
    "lái xe",
    "xe tai",
    "xe khach",
    "xe may",
    "o to",
    "tai xe",
    "lai xe",
    "nồng độ cồn",
    "vượt đèn đỏ",
    "ngược chiều",
    "nong do con",
    "vuot den do",
    "nguoc chieu",
    "kinh doanh vận tải",
    "vận tải hàng hóa",
    "kinh doanh van tai",
    "van tai hang hoa",
]


_ref_vectors: np.ndarray | None = None

_SMALL_TALK_EXACT = {
    "chao",
    "chao ban",
    "hello",
    "hi",
    "hey",
    "xin chao",
    "xin chao ban",
    "cam on",
    "cam on ban",
    "thanks",
    "thank you",
    "ban la ai",
    "ban co the lam gi",
}

_SMALL_TALK_PREFIXES = (
    "chao ",
    "hello ",
    "hi ",
    "xin chao ",
    "cam on ",
)

_LEGAL_DOC_REFERENCE_PATTERN = re.compile(
    r"\b(?:\d{1,3}/(?:\d{4}/(?:QH\d+|NĐ-CP|ND-CP|TT-[A-ZĐ]+|QĐ-[A-ZĐ]+|QD-[A-ZĐ]+)|VBHN-[A-ZĐ]+)|QCVN\s*\d+:\d{4}/[A-ZĐ]+)\b",
    re.IGNORECASE,
)
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

# Stable product-domain concepts. These are intentionally broader than the
# golden dataset and avoid treating generic legal words such as "phạt" as road
# transport by themselves.
_ROAD_DOMAIN_PHRASES = (
    "an toan giao thong",
    "bao hieu duong bo",
    "ben xe",
    "bien bao",
    "bien bao giao thong",
    "bien cam",
    "bien so xe",
    "cap bien so",
    "dang kiem",
    "dang ky xe",
    "duong bo",
    "giay chung nhan kiem dinh",
    "giay phep lai xe",
    "giao thong",
    "ha tang duong bo",
    "hanh lang an toan duong bo",
    "duong cao toc",
    "kiem dinh xe",
    "kiem dinh an toan ky thuat",
    "kiem dinh an toan ky thuat va bao ve moi truong",
    "giay chung nhan kiem dinh",
    "tem kiem dinh",
    "ket cau ha tang duong bo",
    "kinh doanh van tai",
    "khu dong dan cu",
    "lai xe",
    "mo to",
    "mu bao hiem",
    "nguoi dieu khien phuong tien",
    "o to",
    "phuong tien giao thong",
    "sat hach lai xe",
    "sat hach",
    "phan ly thuyet",
    "ly thuyet lai xe",
    "thuc hanh sat hach",
    "suc khoe nguoi lai xe",
    "tai trong xe",
    "toc do khai thac",
    "tram thu phi",
    "van tai duong bo",
    "doi mu bao hiem",
    "xe khach",
    "xe co gioi",
    "xe may",
    "xe may chuyen dung",
    "xe tai",
)

_NON_ROAD_DOMAIN_PHRASES = (
    "bao hiem y te",
    "dang ky doanh nghiep",
    "gia ve may bay",
    "hang khong",
    "hoa don",
    "ho chieu",
    "khung hinh phat",
    "luat giao thong cua singapore",
    "luat giao thong singapore",
    "luat lao dong",
    "ma tuy",
    "mua ban ma tuy",
    "singapore",
    "phat tu",
    "ve may bay",
    "thoi gio lam viec",
    "thue",
    "thi thuc",
    "tien luong",
    "toi pham",
    "xuat nhap canh",
)

_LICENSE_CLASS_PATTERN = re.compile(
    r"\b(?:a1|b1|c1|d1|d2|be|ce|de|c1e|d1e|d2e)\b",
    re.IGNORECASE,
)
_LICENSE_CLASS_CONTEXT = (
    "bang",
    "doi",
    "giay phep",
    "hang",
    "kham suc khoe",
    "sat hach",
)


def _normalize_for_scope(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_punct = re.sub(r"[^a-z0-9\s]", " ", without_marks)
    return re.sub(r"\s+", " ", without_punct).strip()


def is_small_talk_query(query: str) -> bool:
    """Identify harmless conversational turns that should not be legal deflections."""
    normalized = _normalize_for_scope(query)
    if not normalized:
        return False
    if normalized in _SMALL_TALK_EXACT:
        return True
    return len(normalized.split()) <= 5 and normalized.startswith(_SMALL_TALK_PREFIXES)


def _domain_signals(query: str) -> tuple[bool, bool]:
    """Return road-domain and clearly non-road-domain signals."""
    normalized = _normalize_for_scope(query)
    padded = f" {normalized} "

    def contains(phrase: str) -> bool:
        return f" {phrase} " in padded

    if contains("singapore") or contains("luat giao thong cua singapore"):
        return False, True

    has_license_class_context = bool(_LICENSE_CLASS_PATTERN.search(normalized)) and any(
        contains(phrase) for phrase in _LICENSE_CLASS_CONTEXT
    )
    return (
        has_license_class_context or any(contains(phrase) for phrase in _ROAD_DOMAIN_PHRASES),
        any(contains(phrase) for phrase in _NON_ROAD_DOMAIN_PHRASES),
    )


def is_explicit_legal_document_query(query: str) -> bool:
    """Recognize direct legal-document lookups before embedding-based scope classification."""
    query_lower = query.lower()
    if _LEGAL_DOC_REFERENCE_PATTERN.search(query):
        return True
    normalized = _normalize_for_scope(query)
    if not normalized:
        return False
    has_doc_keyword = any(keyword in normalized for keyword in _LEGAL_DOC_KEYWORDS)
    has_doc_abbreviation = bool(_LEGAL_DOC_ABBREVIATION_PATTERN.search(normalized))
    has_short_number = bool(
        _SHORT_DOC_NUMBER_PATTERN.search(query_lower) or _SHORT_QCVN_NUMBER_PATTERN.search(query)
    )
    return (has_doc_keyword or has_doc_abbreviation) and has_short_number


async def _get_ref_vectors() -> np.ndarray:
    global _ref_vectors
    if _ref_vectors is None:
        from src.rag.embedding import embed_texts

        vecs = await embed_texts(_REFERENCE_PHRASES)
        _ref_vectors = np.array(vecs, dtype=np.float32)
        norms = np.linalg.norm(_ref_vectors, axis=1, keepdims=True)
        _ref_vectors = _ref_vectors / norms
    return _ref_vectors


async def classify_scope(query: str) -> ScopeResult:
    """Classify whether a query is in-scope for Vietnamese road transport law."""
    if is_explicit_legal_document_query(query):
        return ScopeResult(label=ScopeLabel.in_scope, score=1.0)

    road_signal, non_road_signal = _domain_signals(query)
    if road_signal and not non_road_signal:
        return ScopeResult(label=ScopeLabel.in_scope, score=1.0)
    if non_road_signal and not road_signal:
        return ScopeResult(label=ScopeLabel.out_of_scope, score=0.0)

    query_vec = np.array(await embed_query(query), dtype=np.float32)
    query_vec = query_vec / np.linalg.norm(query_vec)

    ref_vecs = await _get_ref_vectors()
    similarities = ref_vecs @ query_vec
    # Clamp to [0, 1]: float32 cosine can exceed 1.0 by a rounding epsilon.
    max_sim = float(np.clip(np.max(similarities), 0.0, 1.0))

    query_lower = query.lower()

    # Any legal-document reference should stay in scope without seed-specific IDs.
    if _LEGAL_DOCUMENT_REFERENCE_PATTERN.search(query_lower):
        max_sim = 1.0

    if max_sim >= settings.SCOPE_IN_THRESHOLD:
        label = ScopeLabel.in_scope
    elif max_sim >= settings.SCOPE_UNCERTAIN_THRESHOLD:
        label = ScopeLabel.uncertain
    else:
        label = ScopeLabel.out_of_scope

    return ScopeResult(label=label, score=max_sim)
