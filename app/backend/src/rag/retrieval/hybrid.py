"""Legacy retrieval over ``LegalDocument`` / ``document_chunks``.

The current chat/public runtime must use ``hybrid_legal`` instead. This module is
kept only for legacy maintenance, migration comparison, and targeted tests.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import date

from sqlalchemy import Select, String, bindparam, or_, select, tuple_
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.document_chunk import DocumentChunk
from src.models.legal_document import LegalDocument
from src.schemas.rag import RetrievedChunk

_FTS_UNSAFE_CHARS = re.compile(r"[\\':*!&|<>()~]")
_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d{1,3}/\d{4}/(?:QH\d+|NĐ-CP|ND-CP|TT-[A-ZĐ]+)|QCVN\s*\d+:\d{4}/[A-ZĐ]+)\b",
    re.IGNORECASE,
)
_ARTICLE_PATTERN = re.compile(r"\bđiều\s+(\d+)\b", re.IGNORECASE)
_CLAUSE_PATTERN = re.compile(r"\bkhoản\s+(\d+)\b", re.IGNORECASE)
_POINT_PATTERN = re.compile(r"\bđiểm\s+([a-zđ])\b", re.IGNORECASE)
_SIGN_CODE_PATTERN = re.compile(r"\b([PWRIS])[\s.-]?(\d{2,3}[a-z]?)\b", re.IGNORECASE)
_TECHNICAL_TERMS = ("biển báo", "vạch kẻ", "qcvn", "báo hiệu", "trông như thế nào")
_PENALTY_TERMS = ("mức phạt", "phạt tiền", "xử phạt", "bị phạt")
_EXPLICIT_DOC_QUERY_PATTERN = re.compile(
    r"\b\d{1,3}/(?:\d{4}/(?:QH\d+|NĐ-CP|ND-CP|TT-[A-ZĐ]+|QĐ-[A-ZĐ]+|QD-[A-ZĐ]+)|VBHN-[A-ZĐ]+)\b",
    re.IGNORECASE,
)


_EXPLICIT_DOC_LOOKUP_PATTERN = re.compile(
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


_COMMERCIAL_TRANSPORT_TERMS = (
    "gpkd",
    "kinh doanh van tai",
    "van tai hang hoa",
    "van tai hanh khach",
    "tuyen lien tinh",
    "tuyen co dinh",
    "phu hieu",
    "bien hieu",
    "giay phep kinh doanh",
)
_COMMERCIAL_TRANSPORT_VEHICLES = ("xe tai", "o to", "xe khach", "xe dau keo", "container")
_DOCUMENT_REQUIREMENT_TERMS = (
    "giay to",
    "can gi",
    "can giay to",
    "thu tuc",
    "dieu kien",
    "cap gpkd",
    "cap giay phep",
)
_SAFE_DISTANCE_TERMS = ("khoang cach an toan", "toc do")
_PHONE_PROHIBITION_TERMS = ("dien thoai", "lai xe")
_TRAFFIC_LIGHT_TERMS = ("vuot den do", "den do")
_HELMET_TERMS = ("mu bao hiem", "khong doi mu")
_LICENSE_TERMS = ("khong co giay phep lai xe", "khong co bang lai")
_HIGH_BEAM_TERMS = ("den pha", "den chieu xa")
_ALCOHOL_TERMS = ("nong do con", "uong ruou", "uong bia")
_WRONG_WAY_TERMS = ("di nguoc chieu", "duong mot chieu")
_CAMERA_TERMS = ("camera", "giam sat")
_DRIVING_TIME_TERMS = ("lai toi da", "thoi gian lai xe", "gio ngay", "gio/ngay")
_STRUCTURAL_QUERY_TERMS = (
    "bao gom nhung",
    "bao quat",
    "dieu chinh nhung",
    "dieu kien nen tang",
    "duoc nhan biet",
    "giai thich",
    "gom nhung",
    "khai niem",
    "la gi",
    "pham vi ap dung",
    "quy dinh nhung",
    "van de chinh",
    "y nghia gi",
)
_PENALTY_LOOKUP_TERMS = ("muc phat", "phat tien", "xu phat", "vi pham hanh chinh")
_TRANSPORT_BUSINESS_LOOKUP_TERMS = (
    "kinh doanh van tai",
    "giay phep kinh doanh",
    "phu hieu",
    "bien hieu",
)
_RETRIEVAL_STOP_WORDS = {
    "bao",
    "bi",
    "co",
    "cua",
    "duoc",
    "gi",
    "khong",
    "la",
    "nhieu",
    "theo",
    "va",
    "voi",
}
_SEMANTIC_DOC_REFERENCE_PATTERN = re.compile(
    r"\b(?:(?:nghi\s+dinh|luat|thong\s+tu|nd|nđ|tt)\s+)?"
    r"\d{1,3}/\d{4}(?:/(?:qh\d+|nđ-cp|nd-cp|tt-[a-zđ]+))?\b",
    re.IGNORECASE,
)


def _normalize_sign_code(prefix: str, number: str) -> str:
    return f"{prefix.upper()}.{number.lower()}"


def _normalize_for_lookup(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_punct = re.sub(r"[^a-z0-9\s]", " ", without_marks)
    return re.sub(r"\s+", " ", without_punct).strip()


def _is_explicit_document_lookup(query: str) -> bool:
    if _EXPLICIT_DOC_LOOKUP_PATTERN.search(query):
        return True
    normalized = _normalize_for_lookup(query)
    if not normalized:
        return False
    has_doc_keyword = any(keyword in normalized for keyword in _LEGAL_DOC_KEYWORDS)
    has_doc_abbreviation = bool(_LEGAL_DOC_ABBREVIATION_PATTERN.search(normalized))
    has_short_number = bool(
        _SHORT_DOC_NUMBER_PATTERN.search(query.lower()) or _SHORT_QCVN_NUMBER_PATTERN.search(query)
    )
    return (has_doc_keyword or has_doc_abbreviation) and has_short_number


def _explicit_document_references(query: str) -> set[str]:
    return {
        _normalize_for_lookup(match.group(0))
        for match in _EXPLICIT_DOC_LOOKUP_PATTERN.finditer(query)
    }


def _filter_explicit_document_candidates(query: str, candidates: list[dict]) -> list[dict]:
    """Prevent an explicit document lookup from drifting to similar documents."""
    references = _explicit_document_references(query)
    if not references:
        return candidates
    return [
        candidate
        for candidate in candidates
        if any(
            reference
            in _normalize_for_lookup(
                str(candidate.get("document_number") or candidate.get("doc_title") or "")
            )
            for reference in references
        )
    ]


def expand_query_for_retrieval(query: str) -> str:
    """Add deterministic transport-business hints for underspecified permit queries."""
    normalized = _normalize_for_lookup(query)
    if not normalized:
        return query
    has_vehicle = any(term in normalized for term in _COMMERCIAL_TRANSPORT_VEHICLES)
    has_business = any(term in normalized for term in _COMMERCIAL_TRANSPORT_TERMS)
    has_requirement = any(term in normalized for term in _DOCUMENT_REQUIREMENT_TERMS)
    expansions: list[str] = []
    if any(
        phrase in normalized
        for phrase in (
            "bao quat",
            "dieu chinh nhung",
            "pham vi ap dung",
            "quy dinh nhung",
            "van de chinh",
        )
    ):
        expansions.append(
            "phạm vi điều chỉnh văn bản này quy định thông tư này quy định luật này quy định "
            "pham vi dieu chinh van ban nay quy dinh thong tu nay quy dinh luat nay quy dinh"
        )
    if any(
        phrase in normalized
        for phrase in (
            "bao gom nhung",
            "dieu kien nen tang",
            "duoc nhan biet",
            "giai thich",
            "gom nhung",
            "khai niem",
            "la gi",
            "y nghia gi",
        )
    ):
        expansions.append(
            "giải thích từ ngữ nguyên tắc điều kiện chung là bao gồm "
            "giai thich tu ngu nguyen tac dieu kien chung la bao gom"
        )
    if (has_vehicle or has_business) and (has_business or has_requirement):
        expansions.append(
            "kinh doanh vận tải bằng xe ô tô giấy phép kinh doanh vận tải phù hiệu biển hiệu "
            "kinh doanh van tai bang xe o to giay phep kinh doanh van tai phu hieu bien hieu"
        )
    if all(term in normalized for term in _SAFE_DISTANCE_TERMS):
        expansions.append(
            "khoảng cách an toàn giữa hai xe tốc độ xe chạy giữ khoảng cách an toàn "
            "khoang cach an toan giua hai xe toc do xe chay giu khoang cach an toan"
        )
    if all(term in normalized for term in _PHONE_PROHIBITION_TERMS):
        expansions.append(
            "dùng tay cầm và sử dụng điện thoại khi điều khiển phương tiện đang di chuyển "
            "dung tay cam va su dung dien thoai khi dieu khien phuong tien dang di chuyen"
        )
    if any(term in normalized for term in _TRAFFIC_LIGHT_TERMS):
        expansions.append(
            "không chấp hành hiệu lệnh của đèn tín hiệu giao thông "
            "khong chap hanh hieu lenh cua den tin hieu giao thong"
        )
    if any(term in normalized for term in _HELMET_TERMS):
        expansions.append(
            "người điều khiển xe mô tô xe gắn máy không đội mũ bảo hiểm không cài quai "
            "nguoi dieu khien xe mo to xe gan may khong doi mu bao hiem khong cai quai"
        )
    if any(term in normalized for term in _LICENSE_TERMS):
        expansions.append(
            "người điều khiển xe mô tô không có giấy phép lái xe "
            "nguoi dieu khien xe mo to khong co giay phep lai xe"
        )
    if any(term in normalized for term in _HIGH_BEAM_TERMS):
        expansions.append(
            "sử dụng đèn chiếu xa khi gặp xe đi ngược chiều "
            "su dung den chieu xa khi gap xe di nguoc chieu"
        )
    if any(term in normalized for term in _ALCOHOL_TERMS):
        expansions.append(
            "điều khiển xe trên đường mà trong máu hoặc hơi thở có nồng độ cồn "
            "dieu khien xe trong mau hoac hoi tho co nong do con"
        )
    if any(term in normalized for term in _WRONG_WAY_TERMS):
        expansions.append(
            "đi ngược chiều của đường một chiều đường có biển cấm đi ngược chiều "
            "di nguoc chieu cua duong mot chieu duong co bien cam di nguoc chieu"
        )
    if any(term in normalized for term in _CAMERA_TERMS):
        expansions.append(
            "xe ô tô kinh doanh vận tải hành khách từ 09 chỗ kể cả người lái xe phải lắp camera "
            "xe o to kinh doanh van tai hanh khach tu 09 cho ke ca nguoi lai xe phai lap camera"
        )
    if any(term in normalized for term in _DRIVING_TIME_TERMS):
        expansions.append(
            "thời gian lái xe của người lái xe ô tô không quá 10 giờ trong một ngày "
            "thoi gian lai xe cua nguoi lai xe o to khong qua 10 gio trong mot ngay"
        )
    if expansions:
        return f"{query} " + " ".join(expansions)
    return query


def _is_structural_query(query: str) -> bool:
    normalized = _normalize_for_lookup(query)
    return any(phrase in normalized for phrase in _STRUCTURAL_QUERY_TERMS)


def query_for_local_ranking(query: str) -> str:
    """Drop a cited document number when substantive question text remains."""
    stripped = _SEMANTIC_DOC_REFERENCE_PATTERN.sub(" ", query)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped if len(_normalize_for_lookup(stripped).split()) >= 3 else query


def route_corpora(query: str) -> tuple[str, ...]:
    lowered = query.lower()
    if _is_explicit_document_lookup(query):
        return ("road_law", "cross_domain_selected", "road_technical")
    if _SIGN_CODE_PATTERN.search(query) or any(term in lowered for term in _TECHNICAL_TERMS):
        return ("road_technical",)
    if any(term in lowered for term in _PENALTY_TERMS):
        return ("road_law", "cross_domain_selected")
    return ("road_law", "cross_domain_selected")


def _base_filters(query_date: date, corpora: tuple[str, ...]) -> tuple:
    """Return filters shared by every retrieval branch.

    `status=active` is deliberately present on both tables before ranking.
    """
    return (
        DocumentChunk.status == "active",
        LegalDocument.status == "active",
        DocumentChunk.rag_enabled.is_(True),
        LegalDocument.rag_enabled.is_(True),
        LegalDocument.review_status == "approved",
        DocumentChunk.provision_status == "active",
        DocumentChunk.corpus.in_(corpora),
        or_(DocumentChunk.valid_from.is_(None), DocumentChunk.valid_from <= query_date),
        or_(DocumentChunk.valid_to.is_(None), DocumentChunk.valid_to > query_date),
        or_(LegalDocument.valid_from.is_(None), LegalDocument.valid_from <= query_date),
        or_(LegalDocument.valid_to.is_(None), LegalDocument.valid_to > query_date),
    )


def _candidate_columns() -> tuple:
    return (
        DocumentChunk.chunk_id,
        DocumentChunk.doc_id,
        DocumentChunk.text_content,
        DocumentChunk.chunk_type,
        DocumentChunk.article_num,
        DocumentChunk.clause_num,
        DocumentChunk.point_num,
        DocumentChunk.status,
        DocumentChunk.effective_date,
        DocumentChunk.canonical_provision_id,
        DocumentChunk.locator_type,
        DocumentChunk.locator_label,
        DocumentChunk.section_path,
        DocumentChunk.metadata_json,
        DocumentChunk.section_number,
        DocumentChunk.sign_codes,
        DocumentChunk.asset_ids,
        DocumentChunk.corpus,
        LegalDocument.title.label("doc_title"),
        LegalDocument.doc_type,
        LegalDocument.legal_status,
        LegalDocument.source_url,
        LegalDocument.domain_tags,
        LegalDocument.document_number,
    )


def _row_to_candidate(row, score_name: str, score: float) -> dict:
    metadata = getattr(row, "metadata_json", None) or {}
    section_path = row.section_path or metadata.get("heading_path") or []
    candidate = {
        "chunk_id": row.chunk_id,
        "doc_id": row.doc_id,
        "text_content": row.text_content,
        "chunk_type": row.chunk_type,
        "article_num": row.article_num,
        "clause_num": row.clause_num,
        "point_num": row.point_num,
        "status": row.status,
        "effective_date": row.effective_date,
        "canonical_provision_id": row.canonical_provision_id,
        "locator_type": row.locator_type,
        "locator_label": row.locator_label,
        "section_path": section_path,
        "section_number": row.section_number,
        "sign_codes": row.sign_codes or [],
        "asset_ids": row.asset_ids or [],
        "corpus": row.corpus,
        "doc_title": row.doc_title,
        "doc_type": row.doc_type,
        "legal_status": row.legal_status,
        "source_url": row.source_url,
        "domain_tags": row.domain_tags or [],
        "document_number": row.document_number,
        "vector_score": 0.0,
        "fts_score": 0.0,
        "exact_score": 0.0,
    }
    candidate[score_name] = score
    return candidate


async def _vector_search(
    session: AsyncSession,
    query_embedding: list[float],
    top_k: int,
    query_date: date | None = None,
    corpora: tuple[str, ...] | None = None,
) -> list[dict]:
    query_date = query_date or date.today()
    corpora = corpora or ("road_law", "cross_domain_selected")
    cosine_dist = DocumentChunk.embedding_vector.cosine_distance(query_embedding)
    stmt = (
        select(*_candidate_columns(), (1 - cosine_dist).label("score"))
        .join(LegalDocument, DocumentChunk.doc_id == LegalDocument.doc_id)
        .where(*_base_filters(query_date, corpora))
        .where(DocumentChunk.embedding_vector.isnot(None))
        .order_by(cosine_dist)
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).all()
    return [
        _row_to_candidate(row, "vector_score", max(0.0, min(1.0, float(row.score)))) for row in rows
    ]


def _build_tsquery_string(query: str) -> str:
    sanitized = _FTS_UNSAFE_CHARS.sub(" ", query).strip()
    stop_words = {
        "là",
        "gì",
        "của",
        "và",
        "có",
        "được",
        "trong",
        "cho",
        "theo",
        "bao",
        "nhiêu",
    }
    words: list[str] = []
    seen: set[str] = set()
    for word in re.findall(r"\w+", sanitized.lower()):
        if word in stop_words or len(word) <= 1 or word in seen:
            continue
        words.append(word)
        seen.add(word)
        if len(words) >= max(1, settings.RETRIEVAL_FTS_MAX_TERMS):
            break
    # Quote every generated lexeme so user-provided words such as OR/NOT stay
    # search terms rather than becoming websearch query-language operators.
    return " OR ".join(f'"{word}"' for word in words)


async def _fts_search(
    session: AsyncSession,
    query: str,
    top_k: int,
    query_date: date | None = None,
    corpora: tuple[str, ...] | None = None,
) -> list[dict]:
    query_date = query_date or date.today()
    corpora = corpora or ("road_law", "cross_domain_selected")
    tsquery = _build_tsquery_string(query)
    if not tsquery:
        return []
    sql = sa_text(
        """
        SELECT dc.chunk_id, dc.doc_id, dc.text_content, dc.chunk_type,
               dc.article_num, dc.clause_num, dc.point_num, dc.status,
               dc.effective_date, dc.canonical_provision_id, dc.locator_type,
               dc.locator_label, dc.section_path, dc.metadata_json, dc.section_number,
               dc.sign_codes, dc.asset_ids, dc.corpus, ld.title AS doc_title, ld.doc_type,
               ld.legal_status, ld.source_url, ld.domain_tags, ld.document_number,
               ts_rank(dc.text_tsv, websearch_to_tsquery('simple', :tsquery)) AS score
        FROM document_chunks dc
        JOIN legal_documents ld ON ld.doc_id = dc.doc_id
        WHERE dc.status = 'active'
          AND ld.status = 'active'
          AND dc.rag_enabled = true
          AND ld.rag_enabled = true
          AND ld.review_status = 'approved'
          AND dc.provision_status = 'active'
          AND dc.corpus = ANY(:corpora)
          AND (dc.valid_from IS NULL OR dc.valid_from <= :query_date)
          AND (dc.valid_to IS NULL OR dc.valid_to > :query_date)
          AND (ld.valid_from IS NULL OR ld.valid_from <= :query_date)
          AND (ld.valid_to IS NULL OR ld.valid_to > :query_date)
          AND dc.text_tsv @@ websearch_to_tsquery('simple', :tsquery)
        ORDER BY score DESC
        LIMIT :top_k
        """
    ).bindparams(bindparam("corpora", type_=ARRAY(String())))
    rows = (
        await session.execute(
            sql,
            {
                "tsquery": tsquery,
                "top_k": top_k,
                "query_date": query_date,
                "corpora": list(corpora),
            },
        )
    ).all()
    max_rank = float(rows[0].score) if rows and rows[0].score > 0 else 1.0
    return [_row_to_candidate(row, "fts_score", float(row.score) / max_rank) for row in rows]


async def _exact_search(
    session: AsyncSession,
    query: str,
    top_k: int,
    query_date: date,
    corpora: tuple[str, ...],
) -> list[dict]:
    clauses = []
    document_numbers = _DOC_NUMBER_PATTERN.findall(query)
    if _is_explicit_document_lookup(query):
        document_numbers.extend(_SHORT_DOC_NUMBER_PATTERN.findall(query))
        document_numbers = list(dict.fromkeys(number.strip() for number in document_numbers))
    article_match = _ARTICLE_PATTERN.search(query)
    clause_match = _CLAUSE_PATTERN.search(query)
    point_match = _POINT_PATTERN.search(query)
    sign_match = _SIGN_CODE_PATTERN.search(query)

    if document_numbers:
        clauses.append(
            or_(
                *[
                    LegalDocument.document_number.ilike(f"%{number.strip()}%")
                    for number in document_numbers
                ]
            )
        )
    if article_match:
        clauses.append(DocumentChunk.article_num == int(article_match.group(1)))
    if clause_match:
        clauses.append(DocumentChunk.clause_num == int(clause_match.group(1)))
    if point_match:
        clauses.append(DocumentChunk.point_num == point_match.group(1).lower())
    if sign_match:
        code = _normalize_sign_code(sign_match.group(1), sign_match.group(2))
        clauses.append(DocumentChunk.sign_codes.any(code))
    if not clauses:
        return []

    stmt: Select = (
        select(*_candidate_columns())
        .join(LegalDocument, DocumentChunk.doc_id == LegalDocument.doc_id)
        .where(*_base_filters(query_date, corpora))
        .where(*clauses)
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_candidate(row, "exact_score", 1.0) for row in rows]


def _compute_hybrid_score(candidate: dict, query: str) -> float:
    """Compatibility helper for callers that still inspect pre-fusion scores."""
    if candidate.get("rrf_score") is not None or candidate.get("hybrid_score") is not None:
        return float(candidate.get("rrf_score") or candidate.get("hybrid_score") or 0.0)
    base = settings.HYBRID_VECTOR_WEIGHT * candidate.get(
        "vector_score", 0.0
    ) + settings.HYBRID_FTS_WEIGHT * candidate.get("fts_score", 0.0)
    query_lower = query.lower()
    if candidate.get("doc_type") == "LUAT":
        base += 0.05
    if candidate.get("article_num") and f"điều {candidate['article_num']}" in query_lower:
        base += 0.20
    title = (candidate.get("doc_title") or "").lower()
    query_numbers = _DOC_NUMBER_PATTERN.findall(query)
    query_numbers.extend(re.findall(r"\b\d{1,3}/\d{4}\b", query))
    if any(number.lower() in title for number in query_numbers):
        base += 0.15
    if any(str(tag).lower() in query_lower for tag in candidate.get("domain_tags") or []):
        base += 0.05
    return base


def _candidate_lookup_text(candidate: dict) -> str:
    parts: list[str] = [
        str(candidate.get("text_content") or ""),
        str(candidate.get("doc_title") or ""),
        str(candidate.get("document_family") or ""),
        " ".join(candidate.get("section_path") or []),
    ]
    parts.extend(str(tag) for tag in candidate.get("domain_tags") or [])
    return _normalize_for_lookup(" ".join(parts))


def _lexical_coverage(query: str, candidate_text: str) -> float:
    query_terms = {
        term
        for term in _normalize_for_lookup(query).split()
        if len(term) > 1 and term not in _RETRIEVAL_STOP_WORDS
    }
    if not query_terms:
        return 0.0
    candidate_terms = set(candidate_text.split())
    return len(query_terms & candidate_terms) / len(query_terms)


def _merge_candidates(
    vector_results: list[dict],
    fts_results: list[dict],
    query: str,
    merge_top_k: int,
    exact_results: list[dict] | None = None,
) -> list[dict]:
    """Fuse retrieval branches using weighted RRF and legal-domain relevance signals."""
    exact_results = exact_results or []
    merged: dict[str, dict] = {}
    rrf_k = 60
    branch_weights = {"exact": 2.4, "vector": 1.2, "fts": 1.6}
    for branch_name, branch in (
        ("exact", exact_results),
        ("vector", vector_results),
        ("fts", fts_results),
    ):
        for rank, candidate in enumerate(branch, start=1):
            key = str(candidate["chunk_id"])
            current = merged.setdefault(key, candidate.copy())
            current[f"{branch_name}_rank"] = rank
            current[f"{branch_name}_score"] = candidate.get(f"{branch_name}_score", 0.0)
            current["rrf_score"] = current.get("rrf_score", 0.0) + branch_weights[branch_name] / (
                rrf_k + rank
            )

    max_rrf = sum(branch_weights.values()) / (rrf_k + 1)
    for candidate in merged.values():
        query_lower = query.lower()
        legal_status = str(candidate.get("legal_status") or "")
        lookup_text = _candidate_lookup_text(candidate)
        normalized_rrf = min(1.0, candidate["rrf_score"] / max_rrf)
        vector_score = float(candidate.get("vector_score") or 0.0)
        fts_score = float(candidate.get("fts_score") or 0.0)
        exact_score = float(candidate.get("exact_score") or 0.0)
        lexical_score = _lexical_coverage(query, lookup_text)
        phrase_bonus = 0.04 if _normalize_for_lookup(query) in lookup_text else 0.0
        intent_bonus = 0.0
        if any(term in query_lower for term in _PENALTY_TERMS):
            if any(term in lookup_text for term in _PENALTY_LOOKUP_TERMS):
                intent_bonus += 0.08
            if legal_status == "partially_repealed":
                intent_bonus -= 0.08
        if "giay to" in query_lower or "giấy tờ" in query_lower or "giay phep" in query_lower:
            if any(term in lookup_text for term in _TRANSPORT_BUSINESS_LOOKUP_TERMS):
                intent_bonus += 0.07
        if legal_status == "partially_repealed":
            intent_bonus -= 0.04
        candidate["hybrid_score"] = round(
            max(
                0.0,
                min(
                    1.0,
                    0.38 * normalized_rrf
                    + 0.22 * vector_score
                    + 0.18 * fts_score
                    + 0.12 * lexical_score
                    + 0.10 * exact_score
                    + phrase_bonus
                    + intent_bonus,
                ),
            ),
            6,
        )

    ranked = sorted(merged.values(), key=lambda item: item["hybrid_score"], reverse=True)
    result: list[dict] = []
    per_document: Counter[str] = Counter()
    seen_provisions: set[str] = set()
    seen_hashable_text: set[str] = set()
    for candidate in ranked:
        provision = candidate.get("canonical_provision_id")
        normalized_text = (
            re.sub(r"\s+", " ", candidate.get("text_content") or str(candidate["chunk_id"]))
            .strip()
            .lower()
        )
        if provision and provision in seen_provisions:
            continue
        if normalized_text in seen_hashable_text:
            continue
        document_key = str(candidate.get("doc_id") or candidate["chunk_id"])
        if per_document[document_key] >= settings.RETRIEVAL_MAX_PER_DOCUMENT:
            continue
        result.append(candidate)
        per_document[document_key] += 1
        seen_hashable_text.add(normalized_text)
        if provision:
            seen_provisions.add(provision)
        if len(result) >= merge_top_k:
            break
    return result


def _prepend_clause_intros(candidates: list[dict], parent_rows: list[dict]) -> list[dict]:
    """Attach a clause's penalty/condition intro to its split point chunks."""
    intros = {
        (str(parent["doc_id"]), parent.get("article_num"), parent.get("clause_num")): str(
            parent.get("text_content") or ""
        ).strip()
        for parent in parent_rows
    }
    enriched: list[dict] = []
    for candidate in candidates:
        item = candidate.copy()
        if item.get("point_num") is not None:
            key = (str(item["doc_id"]), item.get("article_num"), item.get("clause_num"))
            intro = intros.get(key)
            body = str(item.get("text_content") or "").strip()
            if intro and not body.startswith(intro):
                item["text_content"] = f"{intro}\n{body}"
        enriched.append(item)
    return enriched


async def _load_clause_intros(
    session: AsyncSession,
    candidates: list[dict],
    query_date: date,
    corpora: tuple[str, ...],
) -> list[dict]:
    keys = {
        (candidate["doc_id"], candidate.get("article_num"), candidate.get("clause_num"))
        for candidate in candidates[:20]
        if candidate.get("point_num") is not None
        and candidate.get("article_num") is not None
        and candidate.get("clause_num") is not None
    }
    if not keys:
        return []
    stmt = (
        select(*_candidate_columns())
        .join(LegalDocument, DocumentChunk.doc_id == LegalDocument.doc_id)
        .where(*_base_filters(query_date, corpora))
        .where(DocumentChunk.chunk_type == "khoan", DocumentChunk.point_num.is_(None))
        .where(
            tuple_(DocumentChunk.doc_id, DocumentChunk.article_num, DocumentChunk.clause_num).in_(
                keys
            )
        )
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_candidate(row, "exact_score", 0.0) for row in rows]


async def _load_structural_anchors(
    session: AsyncSession,
    candidates: list[dict],
    query_date: date,
    corpora: tuple[str, ...],
) -> list[dict]:
    """Load early scope/definition provisions for structurally worded queries."""
    doc_ids = list(
        dict.fromkeys(candidate["doc_id"] for candidate in candidates if candidate.get("doc_id"))
    )[:3]
    if not doc_ids:
        return []
    stmt = (
        select(*_candidate_columns())
        .join(LegalDocument, DocumentChunk.doc_id == LegalDocument.doc_id)
        .where(*_base_filters(query_date, corpora))
        .where(
            DocumentChunk.doc_id.in_(doc_ids),
            DocumentChunk.article_num.between(1, 3),
        )
        .order_by(
            DocumentChunk.doc_id,
            DocumentChunk.article_num,
            DocumentChunk.clause_num.nullsfirst(),
        )
        .limit(60)
    )
    rows = (await session.execute(stmt)).all()
    return [_row_to_candidate(row, "exact_score", 0.0) for row in rows]


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    query_embedding: list[float],
    query_date: date | None = None,
) -> list[RetrievedChunk]:
    query_date = query_date or date.today()
    corpora = route_corpora(query)
    retrieval_query = expand_query_for_retrieval(query)
    # One AsyncSession cannot provision concurrent connections. Parallelize only
    # with independent sessions after benchmarking the production pool impact.
    exact_results = await _exact_search(
        session, query, settings.RETRIEVAL_EXACT_TOP_K, query_date, corpora
    )
    vector_results = await _vector_search(
        session, query_embedding, settings.RETRIEVAL_VECTOR_TOP_K, query_date, corpora
    )
    fts_results = await _fts_search(
        session, retrieval_query, settings.RETRIEVAL_FTS_TOP_K, query_date, corpora
    )
    exact_results = _filter_explicit_document_candidates(query, exact_results)
    vector_results = _filter_explicit_document_candidates(query, vector_results)
    fts_results = _filter_explicit_document_candidates(query, fts_results)
    merged = _merge_candidates(
        vector_results,
        fts_results,
        query,
        settings.RETRIEVAL_MERGE_TOP_K,
        exact_results,
    )
    if merged and _is_structural_query(query):
        anchors = await _load_structural_anchors(session, merged, query_date, corpora)
        seen_chunk_ids = {str(candidate["chunk_id"]) for candidate in merged}
        for anchor in anchors:
            if str(anchor["chunk_id"]) in seen_chunk_ids:
                continue
            anchor["hybrid_score"] = 0.15
            merged.append(anchor)
            seen_chunk_ids.add(str(anchor["chunk_id"]))
    parent_rows = await _load_clause_intros(session, merged, query_date, corpora)
    merged = _prepend_clause_intros(merged, parent_rows)

    return [
        RetrievedChunk(
            chunk_id=str(candidate["chunk_id"]),
            doc_id=str(candidate["doc_id"]),
            doc_title=candidate["doc_title"],
            doc_type=candidate.get("doc_type", ""),
            document_number=candidate.get("document_number"),
            chunk_type=candidate["chunk_type"],
            article_num=candidate.get("article_num"),
            clause_num=candidate.get("clause_num"),
            point_num=candidate.get("point_num"),
            locator_type=candidate.get("locator_type"),
            locator_label=candidate.get("locator_label"),
            section_path=candidate.get("section_path") or [],
            section_number=candidate.get("section_number"),
            sign_codes=candidate.get("sign_codes") or [],
            asset_ids=candidate.get("asset_ids") or [],
            corpus=candidate.get("corpus"),
            canonical_provision_id=candidate.get("canonical_provision_id"),
            status=candidate["status"],
            effective_date=candidate["effective_date"],
            text_snippet=candidate["text_content"][:500],
            full_text=candidate["text_content"],
            source_url=candidate.get("source_url"),
            vector_score=candidate.get("vector_score"),
            fts_score=candidate.get("fts_score"),
            exact_score=candidate.get("exact_score"),
            hybrid_score=candidate.get("hybrid_score"),
        )
        for candidate in merged
    ]
