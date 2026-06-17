"""KB v2 retrieval with eligibility filtering before search/ranking."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import Select, bindparam, func, or_, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.kb_v2 import (
    KbV2CanonicalNode,
    KbV2DocumentRelation,
    KbV2DocumentRevision,
    KbV2LegalDocument,
    KbV2RetrievalUnit,
    KbV2SourceAsset,
)
from src.rag.retrieval.query_utils import semantic_document_scope_numbers
from src.schemas.rag import RetrievedChunk

_FTS_UNSAFE_CHARS = re.compile(r"[\\':*!&|<>()~]")
_LOCATOR_ARTICLE_PATTERN = re.compile(r"\bdieu\s+(\d+)\b", re.IGNORECASE)
_LOCATOR_CLAUSE_PATTERN = re.compile(r"\bkhoan\s+(\d+)\b", re.IGNORECASE)
_LOCATOR_POINT_PATTERN = re.compile(r"\bdiem\s+([a-z])\b", re.IGNORECASE)
_DOC_NUMBER_PATTERN = re.compile(
    r"\b(\d{1,3}/\d{4}/(?:QH\d+|NĐ-CP|ND-CP|TT-[A-ZĐ]+|QĐ-[A-ZĐ]+|QD-[A-ZĐ]+))\b",
    re.IGNORECASE,
)
_MAX_CANDIDATES_PER_DOCUMENT = 8
_DOC_NUMBER_PATTERN = re.compile(r"\b(\d{1,3}/\d{4}/[^\s,.;:!?)]*)", re.IGNORECASE)
_RAW_LOOKUP_STOP_WORDS = {
    "bao",
    "bi",
    "bị",
    "co",
    "có",
    "cua",
    "của",
    "duoc",
    "được",
    "gi",
    "gì",
    "khong",
    "không",
    "la",
    "là",
    "nhung",
    "những",
    "theo",
    "thi",
    "thì",
    "va",
    "và",
    "voi",
    "với",
}


@dataclass(frozen=True)
class KbV2RetrievalResult:
    chunks: list[RetrievedChunk]
    future_notice: str | None = None


def _normalize_for_lookup(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    without_punct = re.sub(r"[^a-z0-9\s/]+", " ", without_marks)
    return re.sub(r"\s+", " ", without_punct).strip()


def _raw_lookup_terms(query: str) -> tuple[str, ...]:
    sanitized = re.sub(r"[^\w\s/]+", " ", query.lower(), flags=re.UNICODE)
    return tuple(
        dict.fromkeys(
            term
            for term in re.split(r"\s+", sanitized)
            if len(term) >= 2 and term not in _RAW_LOOKUP_STOP_WORDS
        )
    )


def _exact_lookup_text(row) -> str:
    return " ".join(
        str(part or "").lower()
        for part in (
            getattr(row, "text", ""),
            getattr(row, "citation_label", ""),
            getattr(row, "doc_title", ""),
            getattr(row, "document_number", ""),
        )
    )


def _exact_body_text(row) -> str:
    text = str(getattr(row, "text", "") or "").lower()
    marker = "noi dung:"
    if marker in text:
        return text.rsplit(marker, 1)[-1].strip()
    return text


def _exact_metadata_text(row) -> str:
    return " ".join(
        str(part or "").lower()
        for part in (
            getattr(row, "citation_label", ""),
            getattr(row, "doc_title", ""),
            getattr(row, "document_number", ""),
        )
    )


def _exact_match_score(
    row,
    terms: tuple[str, ...],
    doc_refs: set[str],
    *,
    definition_intent: bool = False,
) -> float:
    body_text = _exact_body_text(row)
    metadata_text = _exact_metadata_text(row)
    matched_body_terms = sum(1 for term in terms if term in body_text)
    matched_metadata_terms = sum(1 for term in terms if term in metadata_text)
    term_score = matched_body_terms / max(1, len(terms))
    metadata_score = 0.18 * (matched_metadata_terms / max(1, len(terms)))
    phrase_bonus = 0.0
    if len(terms) >= 2:
        adjacent_matches = sum(
            1 for left, right in zip(terms, terms[1:], strict=False) if f"{left} {right}" in body_text
        )
        phrase_bonus = min(0.35, adjacent_matches * 0.10)
    definition_bonus = 0.0
    if definition_intent and phrase_bonus > 0:
        normalized_body = _normalize_for_lookup(body_text)
        if any(
            marker in f" {normalized_body} "
            for marker in (" la ", " bao gom ", " duoc hieu ", " duoc xac dinh ")
        ):
            definition_bonus = 0.18
    doc_number = str(getattr(row, "document_number", "") or "").lower()
    doc_bonus = 0.45 if doc_refs and doc_number in doc_refs else 0.0
    return term_score + metadata_score + phrase_bonus + definition_bonus + doc_bonus


def _is_definition_lookup(query: str) -> bool:
    normalized = _normalize_for_lookup(query)
    return any(
        phrase in f" {normalized} "
        for phrase in (
            " la gi ",
            " khai niem ",
            " giai thich ",
            " duoc hieu ",
            " dinh nghia ",
        )
    )


def _extract_document_refs(query: str) -> tuple[str, ...]:
    refs = [match.group(1).strip().rstrip(".,;:!?") for match in _DOC_NUMBER_PATTERN.finditer(query)]
    return tuple(dict.fromkeys(ref for ref in refs if ref))


def _document_number_variants(ref: str) -> tuple[str, ...]:
    lowered = ref.lower()
    variants = {lowered}
    variants.add(lowered.replace("n\u0111-cp", "nd-cp"))
    variants.add(lowered.replace("nd-cp", "n\u0111-cp"))
    variants.add(lowered.replace("q\u0111-", "qd-"))
    variants.add(lowered.replace("qd-", "q\u0111-"))
    return tuple(sorted(variants))


async def _document_ids_for_explicit_refs(
    session: AsyncSession,
    query: str,
) -> tuple[str, ...] | None:
    refs = _extract_document_refs(query)
    if not refs:
        return None

    variants: set[str] = set()
    for ref in refs:
        variants.update(_document_number_variants(ref))

    stmt = select(KbV2LegalDocument.document_id).where(
        sa_text("lower(kb_v2_legal_documents.document_number) = ANY(:document_numbers)")
    )
    rows = (await session.execute(stmt.params(document_numbers=sorted(variants)))).scalars().all()
    return tuple(dict.fromkeys(rows))


def _base_filters(query_date: date, *, mode: Literal["active", "historical"] = "active") -> tuple:
    shared_filters = (
        KbV2DocumentRevision.review_status == "approved",
        KbV2CanonicalNode.review_status == "approved",
        or_(KbV2RetrievalUnit.effective_from.is_(None), KbV2RetrievalUnit.effective_from <= query_date),
        or_(KbV2RetrievalUnit.effective_to.is_(None), KbV2RetrievalUnit.effective_to > query_date),
    )
    if mode == "historical":
        return (
            KbV2DocumentRevision.publication_status.in_(("published", "suspended", "archived")),
            KbV2RetrievalUnit.answerable_status.in_(("active", "historical")),
            *shared_filters,
        )
    return (
        KbV2DocumentRevision.publication_status == "published",
        KbV2LegalDocument.legal_status == "active",
        KbV2RetrievalUnit.answerable_status == "active",
        *shared_filters,
    )


def _candidate_columns() -> tuple:
    return (
        KbV2RetrievalUnit.retrieval_unit_id,
        KbV2RetrievalUnit.document_id,
        KbV2RetrievalUnit.text,
        KbV2RetrievalUnit.citation_label,
        KbV2RetrievalUnit.metadata_json,
        KbV2RetrievalUnit.answerable_status,
        KbV2RetrievalUnit.effective_from,
        KbV2RetrievalUnit.effective_to,
        KbV2LegalDocument.title.label("doc_title"),
        KbV2LegalDocument.document_number,
        KbV2LegalDocument.document_type,
        KbV2DocumentRevision.source_url.label("revision_source_url"),
        KbV2SourceAsset.source_url.label("asset_source_url"),
    )


def _base_stmt(query_date: date, *, mode: Literal["active", "historical"] = "active") -> Select:
    return (
        select(*_candidate_columns())
        .join(
            KbV2DocumentRevision,
            KbV2DocumentRevision.revision_id == KbV2RetrievalUnit.revision_id,
        )
        .join(
            KbV2CanonicalNode,
            KbV2CanonicalNode.node_id == KbV2RetrievalUnit.canonical_node_id,
        )
        .join(
            KbV2LegalDocument,
            KbV2LegalDocument.document_id == KbV2RetrievalUnit.document_id,
        )
        .outerjoin(
            KbV2SourceAsset,
            KbV2SourceAsset.asset_id == KbV2DocumentRevision.source_asset_id,
        )
        .where(*_base_filters(query_date, mode=mode))
    )


def _parse_locator(citation_label: str | None) -> tuple[int | None, int | None, str | None]:
    if not citation_label:
        return None, None, None
    normalized_label = _normalize_for_lookup(citation_label)
    article_match = _LOCATOR_ARTICLE_PATTERN.search(normalized_label)
    clause_match = _LOCATOR_CLAUSE_PATTERN.search(normalized_label)
    point_match = _LOCATOR_POINT_PATTERN.search(normalized_label)
    return (
        int(article_match.group(1)) if article_match else None,
        int(clause_match.group(1)) if clause_match else None,
        point_match.group(1) if point_match else None,
    )


def _row_to_candidate(
    row,
    score_name: str,
    score: float,
    *,
    mode: Literal["active", "historical"] = "active",
) -> dict:
    metadata = getattr(row, "metadata_json", None) or {}
    citation_label = row.citation_label or metadata.get("label") or ""
    article_num, clause_num, point_num = _parse_locator(citation_label)
    section_path = [part.strip() for part in citation_label.split(">") if part.strip()]
    text = row.text.strip()
    candidate = {
        "chunk_id": row.retrieval_unit_id,
        "doc_id": row.document_id,
        "text_content": text,
        "chunk_type": metadata.get("node_type") or "canonical_node",
        "article_num": article_num,
        "clause_num": clause_num,
        "point_num": point_num,
        "status": "historical" if mode == "historical" else row.answerable_status,
        "effective_date": row.effective_from or date.today(),
        "expiry_date": row.effective_to,
        "canonical_provision_id": None,
        "locator_type": metadata.get("node_type") or "canonical_node",
        "locator_label": citation_label or None,
        "section_path": section_path,
        "section_number": str(article_num) if article_num is not None else None,
        "sign_codes": [],
        "asset_ids": [],
        "corpus": "kb_v2",
        "doc_title": row.doc_title or "Chưa rõ",
        "doc_type": row.document_type or "",
        "source_url": row.asset_source_url or row.revision_source_url,
        "document_number": row.document_number,
        "vector_score": 0.0,
        "fts_score": 0.0,
        "exact_score": 0.0,
    }
    candidate[score_name] = score
    return candidate


async def _vector_search(
    session: AsyncSession,
    *,
    query_embedding: list[float],
    query_date: date,
    top_k: int,
    document_ids: tuple[str, ...] | None,
    mode: Literal["active", "historical"] = "active",
) -> list[dict]:
    cosine_dist = KbV2RetrievalUnit.embedding_vector.cosine_distance(query_embedding)
    stmt = (
        _base_stmt(query_date, mode=mode)
        .where(KbV2RetrievalUnit.embedding_vector.isnot(None))
        .order_by(cosine_dist)
        .limit(top_k)
    )
    if document_ids:
        stmt = stmt.where(KbV2RetrievalUnit.document_id.in_(document_ids))
    rows = (await session.execute(stmt.add_columns((1 - cosine_dist).label("score")))).all()
    return [
        _row_to_candidate(
            row,
            "vector_score",
            max(0.0, min(1.0, float(row.score))),
            mode=mode,
        )
        for row in rows
    ]


def _build_tsquery_string(query: str) -> str:
    sanitized = _FTS_UNSAFE_CHARS.sub(" ", query).strip()
    terms = [term for term in re.split(r"\s+", sanitized) if len(term) >= 2]
    limited_terms = terms[: settings.RETRIEVAL_FTS_MAX_TERMS]
    return " & ".join(f"{term}:*" for term in limited_terms) if limited_terms else ""


async def _fts_search(
    session: AsyncSession,
    *,
    query: str,
    query_date: date,
    top_k: int,
    document_ids: tuple[str, ...] | None,
    mode: Literal["active", "historical"] = "active",
) -> list[dict]:
    tsquery = _build_tsquery_string(query)
    if not tsquery:
        return []
    stmt = _base_stmt(query_date, mode=mode)
    if document_ids:
        stmt = stmt.where(KbV2RetrievalUnit.document_id.in_(document_ids))
    tsquery_param = bindparam("tsquery")
    tsvector = func.to_tsvector("simple", KbV2RetrievalUnit.text)
    tsquery_expr = func.to_tsquery("simple", tsquery_param)
    score_expr = func.ts_rank_cd(tsvector, tsquery_expr).label("score")
    stmt = (
        stmt.add_columns(score_expr)
        .where(tsvector.op("@@")(tsquery_expr))
        .params(tsquery=tsquery)
        .order_by(sa_text("score DESC"))
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).all()
    max_score = max((float(row._mapping["score"]) for row in rows), default=1.0) or 1.0
    return [
        _row_to_candidate(
            row,
            "fts_score",
            max(0.0, min(1.0, float(row._mapping["score"]) / max_score)),
            mode=mode,
        )
        for row in rows
    ]


async def _exact_search(
    session: AsyncSession,
    *,
    query: str,
    query_date: date,
    top_k: int,
    document_ids: tuple[str, ...] | None,
    mode: Literal["active", "historical"] = "active",
) -> list[dict]:
    terms = _raw_lookup_terms(query)
    doc_refs = {
        variant
        for ref in _extract_document_refs(query)
        for variant in _document_number_variants(ref)
    }
    if not terms and not doc_refs:
        return []

    clauses = []
    params: dict[str, object] = {}
    for index, term in enumerate(terms[:10]):
        key = f"term_{index}"
        clauses.append(
            sa_text(
                "("
                f"lower(kb_v2_retrieval_units.text) LIKE :{key} "
                f"OR lower(kb_v2_retrieval_units.citation_label) LIKE :{key} "
                f"OR lower(kb_v2_legal_documents.title) LIKE :{key}"
                ")"
            )
        )
        params[key] = f"%{term}%"
    if doc_refs:
        clauses.append(sa_text("lower(kb_v2_legal_documents.document_number) = ANY(:doc_refs)"))
        params["doc_refs"] = list(doc_refs)
    stmt = _base_stmt(query_date, mode=mode)
    if document_ids:
        stmt = stmt.where(KbV2RetrievalUnit.document_id.in_(document_ids))
    fetch_limit = max(top_k * 40, 500)
    stmt = stmt.where(or_(*clauses)).params(**params).limit(fetch_limit)
    rows = (await session.execute(stmt)).all()
    definition_intent = _is_definition_lookup(query)
    ranked = sorted(
        rows,
        key=lambda row: _exact_match_score(
            row,
            terms,
            doc_refs,
            definition_intent=definition_intent,
        ),
        reverse=True,
    )
    return [
        _row_to_candidate(
            row,
            "exact_score",
            min(
                1.0,
                _exact_match_score(
                    row,
                    terms,
                    doc_refs,
                    definition_intent=definition_intent,
                ),
            ),
            mode=mode,
        )
        for row in ranked[:top_k]
    ]


def _topic_supplement_locators(query: str) -> tuple[tuple[str, int, int | None], ...]:
    """Return high-confidence active units that should accompany known topics."""
    normalized = _normalize_for_lookup(query)
    supplements: list[tuple[str, int, int | None]] = []

    if "kiem dinh an toan ky thuat" in normalized and "la gi" in normalized:
        supplements.append(("16/2021/TT-BGTVT", 3, 1))
    definition_query = any(
        phrase in normalized for phrase in ("la gi", "duoc hieu", "khai niem", "dinh nghia")
    )
    if "duong cao toc" in normalized and definition_query:
        supplements.append(("35/2024/QH15", 44, 1))
    elif "duong cao toc" in normalized:
        supplements.append(("36/2024/QH15", 25, 1))
    if "hanh lang an toan duong bo" in normalized and definition_query:
        supplements.append(("35/2024/QH15", 2, 5))
    if "ket cau ha tang duong bo" in normalized and any(
        phrase in normalized for phrase in ("gom", "bao gom", "la gi")
    ):
        supplements.append(("35/2024/QH15", 2, 4))
    if "luat duong bo" in normalized and any(
        phrase in normalized for phrase in ("noi dung chinh", "nhom noi dung")
    ):
        supplements.append(("35/2024/QH15", 2, 1))
    elif "luat duong bo" in normalized and any(
        phrase in normalized for phrase in ("dieu chinh", "pham vi")
    ):
        supplements.extend((("35/2024/QH15", 1, None), ("35/2024/QH15", 2, 1)))
    if ("luat trat tu" in normalized or "luat ve trat tu" in normalized) and any(
        phrase in normalized for phrase in ("tap trung", "bao quat", "nhom van de", "pham vi")
    ):
        supplements.append(("36/2024/QH15", 1, None))

    if any(
        phrase in normalized
        for phrase in (
            "bai thuc hanh co ban",
            "4 bai thuc hanh",
            "bon bai thuc hanh",
            "thuc hanh sat hach mo to",
            "nguoi sat hach giay phep lai xe hang a1",
        )
    ):
        supplements.append(("108/2026/TT-BCA", 4, 2))

    if any(
        phrase in normalized
        for phrase in ("phan ly thuyet", "ly thuyet kiem tra", "sat hach ly thuyet")
    ):
        supplements.append(("108/2026/TT-BCA", 14, 1))

    has_registration = "dang ky xe" in normalized
    has_inspection = any(
        phrase in normalized
        for phrase in (
            "kiem dinh xe",
            "kiem dinh an toan ky thuat",
            "giay chung nhan kiem dinh",
        )
    )
    asks_distinction = any(
        phrase in normalized
        for phrase in ("khac nhau", "phan biet", "xac nhan hai van de")
    )
    if has_registration and has_inspection and asks_distinction:
        supplements.extend(
            (
                ("79/2024/TT-BCA", 3, 1),
                ("16/2021/TT-BGTVT", 3, 1),
                ("16/2021/TT-BGTVT", 3, 2),
            )
        )
    if has_registration and any(
        phrase in normalized
        for phrase in (
            "nop o dau",
            "noi nop ho so",
            "dia diem nop",
            "co quan dang ky xe",
            "tiep nhan ho so",
        )
    ):
        supplements.append(("79/2024/TT-BCA", 3, 4))
    if "luat duong bo" in normalized and "luat trat tu" in normalized:
        supplements.extend(
            (
                ("35/2024/QH15", 1, None),
                ("36/2024/QH15", 1, None),
            )
        )
    if "luat nen" in normalized and "thu tuc dang ky" in normalized:
        supplements.extend(
            (
                ("36/2024/QH15", 2, 2),
                ("79/2024/TT-BCA", 3, 1),
            )
        )
    if has_registration and has_inspection and "kinh doanh van tai" in normalized:
        supplements.extend(
            (
                ("79/2024/TT-BCA", 3, 1),
                ("16/2021/TT-BGTVT", 3, 1),
                ("158/2024/NĐ-CP", 1, None),
            )
        )

    return tuple(dict.fromkeys(supplements))


async def _topic_supplement_search(
    session: AsyncSession,
    *,
    query: str,
    query_date: date,
    document_ids: tuple[str, ...] | None,
    mode: Literal["active", "historical"] = "active",
) -> list[dict]:
    locators = _topic_supplement_locators(query)
    if not locators:
        return []

    candidates: list[dict] = []
    for document_number, article_num, clause_num in locators:
        stmt = (
            _base_stmt(query_date, mode=mode)
            .where(
                KbV2LegalDocument.document_number == document_number,
                KbV2RetrievalUnit.citation_label.ilike(f"%Điều {article_num}%"),
            )
            .limit(80)
        )
        if document_ids is not None:
            stmt = stmt.where(KbV2RetrievalUnit.document_id.in_(document_ids))
        rows = (await session.execute(stmt)).all()
        exact_rows = [
            item
            for item in rows
            if _parse_locator(getattr(item, "citation_label", None))[0] == article_num
            and _parse_locator(getattr(item, "citation_label", None))[1] == clause_num
            and "thông tin ban hành" not in str(getattr(item, "citation_label", "")).lower()
        ]
        row = next(
            (
                item
                for item in exact_rows
                if article_num <= 3
                and str(getattr(item, "citation_label", "")).lower().startswith("chương 1")
            ),
            exact_rows[0] if exact_rows else None,
        )
        if row is not None:
            candidates.append(_row_to_candidate(row, "exact_score", 1.0, mode=mode))
    return candidates


def _merge_candidates(*candidate_groups: list[dict]) -> list[RetrievedChunk]:
    merged: dict[str, dict] = {}
    for group in candidate_groups:
        for candidate in group:
            bucket = merged.setdefault(candidate["chunk_id"], candidate)
            for score_name in ("vector_score", "fts_score", "exact_score"):
                bucket[score_name] = max(
                    float(bucket.get(score_name) or 0.0),
                    float(candidate.get(score_name) or 0.0),
                )

    for candidate in merged.values():
        candidate["hybrid_score"] = (
            settings.HYBRID_VECTOR_WEIGHT * float(candidate.get("vector_score") or 0.0)
            + settings.HYBRID_FTS_WEIGHT * float(candidate.get("fts_score") or 0.0)
            + float(candidate.get("exact_score") or 0.0)
        )

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("hybrid_score") or 0.0),
            float(item.get("exact_score") or 0.0),
        ),
        reverse=True,
    )
    per_document: Counter[str] = Counter()
    selected: list[RetrievedChunk] = []
    for candidate in ranked:
        if len(selected) >= settings.RETRIEVAL_MERGE_TOP_K:
            break
        if per_document[candidate["doc_id"]] >= min(
            settings.RETRIEVAL_MAX_PER_DOCUMENT, _MAX_CANDIDATES_PER_DOCUMENT
        ):
            continue
        per_document[candidate["doc_id"]] += 1
        selected.append(
            RetrievedChunk(
                chunk_id=candidate["chunk_id"],
                doc_id=candidate["doc_id"],
                doc_title=candidate["doc_title"],
                doc_type=candidate["doc_type"],
                document_number=candidate["document_number"],
                chunk_type=candidate["chunk_type"],
                article_num=candidate["article_num"],
                clause_num=candidate["clause_num"],
                point_num=candidate["point_num"],
                locator_type=candidate["locator_type"],
                locator_label=candidate["locator_label"],
                section_path=candidate["section_path"],
                section_number=candidate["section_number"],
                sign_codes=candidate["sign_codes"],
                asset_ids=candidate["asset_ids"],
                corpus=candidate["corpus"],
                canonical_provision_id=None,
                status=candidate["status"],
                effective_date=candidate["effective_date"],
                expiry_date=candidate.get("expiry_date"),
                text_snippet=candidate["text_content"][:500],
                full_text=candidate["text_content"],
                source_url=candidate["source_url"],
                vector_score=candidate["vector_score"],
                fts_score=candidate["fts_score"],
                exact_score=candidate["exact_score"],
                hybrid_score=candidate["hybrid_score"],
            )
        )
    return selected


async def hybrid_retrieve_v2(
    session: AsyncSession,
    query: str,
    query_embedding: list[float],
    *,
    query_date: date,
    document_ids: tuple[str, ...] | None = None,
    mode: Literal["active", "historical"] = "active",
) -> KbV2RetrievalResult:
    scoped_document_ids = document_ids
    if scoped_document_ids is None:
        scoped_document_ids = await _document_ids_for_explicit_refs(session, query)
        if scoped_document_ids == ():
            return KbV2RetrievalResult(chunks=[])
    if scoped_document_ids is None:
        semantic_numbers = semantic_document_scope_numbers(query)
        if semantic_numbers:
            scoped_document_ids = await _document_ids_for_explicit_refs(
                session,
                " ".join(semantic_numbers),
            )
            if scoped_document_ids == ():
                return KbV2RetrievalResult(chunks=[])

    vector_candidates = await _vector_search(
        session,
        query_embedding=query_embedding,
        query_date=query_date,
        top_k=settings.RETRIEVAL_VECTOR_TOP_K,
        document_ids=scoped_document_ids,
        mode=mode,
    )
    fts_candidates = await _fts_search(
        session,
        query=query,
        query_date=query_date,
        top_k=settings.RETRIEVAL_FTS_TOP_K,
        document_ids=scoped_document_ids,
        mode=mode,
    )
    exact_candidates = await _exact_search(
        session,
        query=query,
        query_date=query_date,
        top_k=settings.RETRIEVAL_EXACT_TOP_K,
        document_ids=scoped_document_ids,
        mode=mode,
    )
    supplement_candidates = await _topic_supplement_search(
        session,
        query=query,
        query_date=query_date,
        document_ids=scoped_document_ids,
        mode=mode,
    )
    return KbV2RetrievalResult(
        chunks=_merge_candidates(
            supplement_candidates,
            vector_candidates,
            fts_candidates,
            exact_candidates,
        )
    )


async def future_effective_notice_for_query(
    session: AsyncSession,
    *,
    query: str,
    reference_date: date,
    document_ids: tuple[str, ...] | None = None,
) -> str | None:
    normalized = _normalize_for_lookup(query)
    if not normalized:
        return None

    stmt = (
        select(
            KbV2LegalDocument.title,
            KbV2LegalDocument.document_number,
            KbV2LegalDocument.effective_date,
        )
        .join(
            KbV2DocumentRevision,
            KbV2DocumentRevision.document_id == KbV2LegalDocument.document_id,
        )
        .where(
            KbV2DocumentRevision.publication_status == "published",
            KbV2LegalDocument.effective_date.is_not(None),
            KbV2LegalDocument.effective_date > reference_date,
        )
        .order_by(KbV2LegalDocument.effective_date.asc())
        .limit(3)
    )
    if document_ids:
        stmt = stmt.where(KbV2LegalDocument.document_id.in_(document_ids))
    rows = (await session.execute(stmt)).all()
    matches = [
        row
        for row in rows
        if any(
            token in _normalize_for_lookup(" ".join(filter(None, [row.title, row.document_number])))
            for token in normalized.split()
            if len(token) >= 4
        )
    ]
    if not matches:
        return None
    row = matches[0]
    effective_date = row.effective_date.strftime("%d/%m/%Y") if row.effective_date else "chưa rõ"
    label = row.document_number or row.title or "văn bản đang được hỏi"
    return (
        f"Văn bản {label} chưa có hiệu lực tại ngày {reference_date.strftime('%d/%m/%Y')}. "
        f"Ngày có hiệu lực dự kiến: {effective_date}."
    )


async def related_document_ids(
    session: AsyncSession,
    *,
    document_id: str,
) -> tuple[str, ...]:
    stmt = select(KbV2DocumentRelation).where(
        or_(
            KbV2DocumentRelation.source_document_id == document_id,
            KbV2DocumentRelation.target_document_id == document_id,
        )
    )
    relations = (await session.execute(stmt)).scalars().all()
    related = {document_id}
    for relation in relations:
        review_status = str((relation.metadata_json or {}).get("review_status") or "needs_review")
        if review_status != "approved":
            continue
        related.add(relation.source_document_id)
        related.add(relation.target_document_id)
    return tuple(sorted(related))
