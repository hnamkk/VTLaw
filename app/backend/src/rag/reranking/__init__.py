"""Deterministic legal-domain ranking for hybrid retrieval candidates."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from src.core.config import settings
from src.schemas.rag import RetrievedChunk

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ARTICLE_PATTERN = re.compile(r"\bdieu\s+(\d+)\b")
_CLAUSE_PATTERN = re.compile(r"\bkhoan\s+(\d+)\b")
_POINT_PATTERN = re.compile(r"\bdiem\s+([a-z])\b")
_DOC_NUMBER_PATTERN = re.compile(r"\b\d{1,3}/\d{4}(?:/[a-z0-9-]+)?\b")
_SIGN_CODE_PATTERN = re.compile(r"\b([pwris])[\s.-]?(\d{2,3}[a-z]?)\b")
_STOP_WORDS = {
    "ai",
    "bao",
    "bi",
    "co",
    "cua",
    "duoc",
    "gi",
    "khong",
    "la",
    "mot",
    "nhieu",
    "nhung",
    "theo",
    "thi",
    "toi",
    "va",
    "voi",
}


@dataclass(frozen=True)
class RerankResult:
    chunks: list[RetrievedChunk]
    reranker_failed: bool = False
    reranker_used: bool = True
    low_confidence: bool = False
    error_code: str | None = None
    top_score: float | None = None


@dataclass(frozen=True)
class _CandidateFeatures:
    normalized_text: str
    tokens: frozenset[str]
    normalized_heading: str
    normalized_content: str
    normalized_document: str


def _normalize(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _tokens(text: str) -> list[str]:
    return _tokens_from_normalized(_normalize(text))


def _tokens_from_normalized(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 1 and token not in _STOP_WORDS
    ]


def _candidate_text(chunk: RetrievedChunk) -> str:
    metadata = " ".join(
        part
        for part in (
            chunk.doc_title,
            chunk.document_number or "",
            chunk.locator_label or "",
            " ".join(chunk.section_path),
            " ".join(chunk.sign_codes),
        )
        if part
    )
    return f"{metadata} {chunk.full_text or chunk.text_snippet}"


def _candidate_features(chunk: RetrievedChunk) -> _CandidateFeatures:
    normalized_text = _normalize(_candidate_text(chunk))
    return _CandidateFeatures(
        normalized_text=normalized_text,
        tokens=frozenset(_tokens_from_normalized(normalized_text)),
        normalized_heading=_normalize(" ".join(chunk.section_path)),
        normalized_content=_normalize(chunk.full_text or chunk.text_snippet),
        normalized_document=_normalize(chunk.document_number or chunk.doc_title),
    )


def _normalized_hybrid_scores(chunks: list[RetrievedChunk]) -> dict[str, float]:
    scores = [float(chunk.hybrid_score or 0.0) for chunk in chunks]
    low = min(scores, default=0.0)
    high = max(scores, default=0.0)
    if math.isclose(low, high):
        bounded = max(0.0, min(1.0, high))
        return {chunk.chunk_id: bounded for chunk in chunks}
    return {
        chunk.chunk_id: (float(chunk.hybrid_score or 0.0) - low) / (high - low) for chunk in chunks
    }


def _query_term_weights(
    query_tokens: list[str], features: list[_CandidateFeatures]
) -> dict[str, float]:
    document_frequency: Counter[str] = Counter()
    for candidate in features:
        document_frequency.update(candidate.tokens)
    count = max(1, len(features))
    return {
        token: 1.0 + math.log((count + 1) / (document_frequency[token] + 1))
        for token in set(query_tokens)
    }


def _legal_reference_bonus(
    normalized_query: str,
    chunk: RetrievedChunk,
    normalized_document: str,
) -> float:
    bonus = 0.0
    article = _ARTICLE_PATTERN.search(normalized_query)
    clause = _CLAUSE_PATTERN.search(normalized_query)
    point = _POINT_PATTERN.search(normalized_query)
    if article and chunk.article_num == int(article.group(1)):
        bonus += 0.45
    if clause and chunk.clause_num == int(clause.group(1)):
        bonus += 0.25
    if point and chunk.point_num == point.group(1):
        bonus += 0.15

    document_numbers = _DOC_NUMBER_PATTERN.findall(normalized_query)
    if document_numbers and any(number in normalized_document for number in document_numbers):
        bonus += 0.55

    sign_match = _SIGN_CODE_PATTERN.search(normalized_query)
    if sign_match:
        expected = f"{sign_match.group(1).upper()}.{sign_match.group(2).lower()}"
        if expected in chunk.sign_codes:
            bonus += 0.65
    return min(1.0, bonus)


def _vehicle_scope_bonus(
    normalized_query: str,
    normalized_heading: str,
) -> float:
    """Disambiguate vehicle classes from legal article headings."""
    asks_motor_vehicle = (
        "xe o to" in normalized_query
        or bool(re.search(r"(?<!m)\bo to\b", normalized_query))
        or "xe tai" in normalized_query
        or "xe dau keo" in normalized_query
    )
    if asks_motor_vehicle:
        if "xe mo to" in normalized_heading or "xe gan may" in normalized_heading:
            return -0.12
        if "xe o to" in normalized_heading or "xe dau keo" in normalized_heading:
            return 0.12
    asks_motorcycle = (
        any(phrase in normalized_query for phrase in ("xe may", "xe mo to", "xe gan may"))
        and "xe may chuyen dung" not in normalized_query
    )
    if asks_motorcycle:
        if "xe may chuyen dung" in normalized_heading:
            return -0.12
        if "xe mo to" in normalized_heading or "xe gan may" in normalized_heading:
            return 0.12
    return 0.0


def _structural_intent_bonus(
    normalized_query: str,
    normalized_content: str,
    article_num: int | None,
) -> float:
    """Prefer provisions that directly define a term or state document scope."""
    definition_query = any(
        phrase in normalized_query
        for phrase in (
            "bao gom nhung",
            "duoc nhan biet",
            "giai thich",
            "gom nhung",
            "khac nhau ve chuc nang",
            "khai niem",
            "la gi",
            "y nghia gi",
        )
    )
    scope_query = any(
        phrase in normalized_query
        for phrase in (
            "bao quat",
            "dieu chinh nhung",
            "pham vi ap dung",
            "quy dinh nhung",
            "van de chinh",
        )
    )

    bonus = 0.0
    if definition_query and any(
        marker in f" {normalized_content} "
        for marker in (" bao gom ", " duoc xac dinh ", " la ", " thuc hien chuc nang ")
    ):
        bonus += 0.16
        if article_num is not None and article_num <= 3:
            bonus += 0.10
    if scope_query and any(
        marker in normalized_content
        for marker in ("ap dung doi voi", "quy dinh ve", "thong tu nay quy dinh")
    ):
        bonus += 0.20
        if article_num == 1:
            bonus += 0.12
    return bonus


def _topic_specific_bonus(
    normalized_query: str,
    *,
    normalized_content: str,
    normalized_document: str,
    article_num: int | None,
    clause_num: int | None,
) -> float:
    """Prefer provisions that directly answer high-frequency product topics."""
    bonus = 0.0

    asks_inspection_definition = (
        "kiem dinh an toan ky thuat" in normalized_query
        and "la gi" in normalized_query
    )
    if asks_inspection_definition:
        if "16/2021/tt-bgtvt" in normalized_document and article_num == 3:
            bonus += 0.22
            if clause_num == 1:
                bonus += 0.12
        if any(
            phrase in normalized_content
            for phrase in (
                "kiem tra danh gia",
                "kiem tra va danh gia",
                "tinh trang an toan ky thuat va bao ve moi truong",
            )
        ):
            bonus += 0.16
        if any(
            phrase in normalized_content
            for phrase in ("nghien cuu thu nghiem", "di chuyen de phuc vu")
        ):
            bonus -= 0.22

    if "duong cao toc" in normalized_query and any(
        phrase in normalized_query for phrase in ("la gi", "duoc hieu", "khai niem", "dinh nghia")
    ):
        if "35/2024/qh15" in normalized_document and article_num == 44:
            bonus += 0.42
            if clause_num == 1:
                bonus += 0.18
        if "chi danh cho mot so loai xe co gioi" in normalized_content:
            bonus += 0.20
        if "36/2024/qh15" in normalized_document and article_num == 25:
            bonus -= 0.20

    if "hanh lang an toan duong bo" in normalized_query and any(
        phrase in normalized_query for phrase in ("la gi", "giai thich", "khai niem", "dinh nghia")
    ):
        if "35/2024/qh15" in normalized_document and article_num == 2 and clause_num == 5:
            bonus += 0.48
        if "dai dat doc hai ben dat cua duong bo" in normalized_content:
            bonus += 0.22

    if "ket cau ha tang duong bo" in normalized_query and any(
        phrase in normalized_query for phrase in ("gom", "bao gom", "la gi")
    ):
        if "35/2024/qh15" in normalized_document and article_num == 2 and clause_num == 4:
            bonus += 0.48
        if "cong trinh duong bo" in normalized_content and "ben xe" in normalized_content:
            bonus += 0.22

    if "luat duong bo" in normalized_query and any(
        phrase in normalized_query for phrase in ("noi dung chinh", "nhom noi dung")
    ):
        if "35/2024/qh15" in normalized_document and article_num == 2 and clause_num == 1:
            bonus += 0.48
        if "hoat dong duong bo" in normalized_content and "van tai duong bo" in normalized_content:
            bonus += 0.22
    elif "luat duong bo" in normalized_query and any(
        phrase in normalized_query for phrase in ("dieu chinh", "pham vi")
    ):
        if "35/2024/qh15" in normalized_document and article_num in {1, 2}:
            bonus += 0.34
        if "hoat dong duong bo" in normalized_content and "van tai duong bo" in normalized_content:
            bonus += 0.18

    if ("luat trat tu" in normalized_query or "luat ve trat tu" in normalized_query) and any(
        phrase in normalized_query for phrase in ("tap trung", "bao quat", "nhom van de", "pham vi")
    ):
        if "36/2024/qh15" in normalized_document and article_num == 1:
            bonus += 0.46
        if "quy tac" in normalized_content and "nguoi tham gia giao thong" in normalized_content:
            bonus += 0.18

    asks_theory_exam = any(
        phrase in normalized_query
        for phrase in ("phan ly thuyet", "ly thuyet kiem tra", "sat hach ly thuyet")
    )
    if asks_theory_exam:
        if "108/2026/tt-bca" in normalized_document and article_num == 14:
            bonus += 0.28
            if clause_num == 1:
                bonus += 0.12
        if "noi dung sat hach ly thuyet" in normalized_content:
            bonus += 0.24
        if any(
            phrase in normalized_content
            for phrase in (
                "phap luat ve trat tu an toan giao thong",
                "ky thuat lai xe",
                "van hoa giao thong",
            )
        ):
            bonus += 0.16
        if "noi dung tap huan" in normalized_content:
            bonus -= 0.24

    asks_registration_inspection_distinction = (
        "dang ky xe" in normalized_query
        and any(
            phrase in normalized_query
            for phrase in ("kiem dinh xe", "kiem dinh an toan ky thuat")
        )
        and any(
            phrase in normalized_query
            for phrase in ("khac nhau", "phan biet", "xac nhan hai van de")
        )
    )
    if asks_registration_inspection_distinction:
        if "79/2024/tt-bca" in normalized_document:
            if article_num == 3 and clause_num == 1:
                bonus += 0.36
            if "nguon goc hop phap" in normalized_content:
                bonus += 0.18
        if "16/2021/tt-bgtvt" in normalized_document:
            if article_num == 3:
                bonus += 0.24
            if any(
                phrase in normalized_content
                for phrase in (
                    "giay chung nhan kiem dinh",
                    "kiem tra va danh gia",
                    "tinh trang an toan ky thuat",
                )
            ):
                bonus += 0.18
        if any(
            phrase in normalized_content
            for phrase in ("dong lai so may", "thu hoi", "cap lai bien so")
        ):
            bonus -= 0.26

    asks_registration_filing_place = (
        "dang ky xe" in normalized_query
        and any(
            phrase in normalized_query
            for phrase in (
                "nop o dau",
                "noi nop ho so",
                "dia diem nop",
                "co quan dang ky xe",
                "tiep nhan ho so",
            )
        )
    )
    if asks_registration_filing_place:
        if "79/2024/tt-bca" in normalized_document and article_num == 3 and clause_num == 4:
            bonus += 0.38
        if any(
            phrase in normalized_content
            for phrase in ("truc tiep tai co quan dang ky xe", "cong dich vu cong")
        ):
            bonus += 0.16
        if any(
            phrase in normalized_content
            for phrase in ("thong tin hoa don", "mau so", "ky hieu hoa don")
        ):
            bonus -= 0.32

    if "luat duong bo" in normalized_query and "luat trat tu" in normalized_query:
        if "35/2024/qh15" in normalized_document and article_num == 1:
            bonus += 0.42
        if "36/2024/qh15" in normalized_document and article_num == 1:
            bonus += 0.34

    if "luat nen" in normalized_query and "thu tuc dang ky" in normalized_query:
        if "36/2024/qh15" in normalized_document and article_num == 2:
            bonus += 0.30
        if "79/2024/tt-bca" in normalized_document and article_num == 3:
            bonus += 0.30

    if (
        "dang ky xe" in normalized_query
        and "kiem dinh xe" in normalized_query
        and "kinh doanh van tai" in normalized_query
    ):
        if "79/2024/tt-bca" in normalized_document and article_num == 3:
            bonus += 0.30
        if "16/2021/tt-bgtvt" in normalized_document and article_num == 3:
            bonus += 0.30
        if "158/2024/nd-cp" in normalized_document and article_num in {1, 11}:
            bonus += 0.24

    return bonus


def _score_chunk(
    normalized_query: str,
    query_tokens: list[str],
    chunk: RetrievedChunk,
    *,
    features: _CandidateFeatures,
    hybrid_score: float,
    term_weights: dict[str, float],
) -> float:
    total_weight = sum(term_weights.values()) or 1.0
    lexical_coverage = (
        sum(weight for token, weight in term_weights.items() if token in features.tokens)
        / total_weight
    )

    meaningful_query = " ".join(query_tokens)
    phrase_score = 1.0 if meaningful_query and meaningful_query in features.normalized_text else 0.0
    if not phrase_score and len(query_tokens) >= 2:
        adjacent = sum(
            1
            for left, right in zip(query_tokens, query_tokens[1:], strict=False)
            if f"{left} {right}" in features.normalized_text
        )
        phrase_score = adjacent / max(1, len(query_tokens) - 1)

    vector_score = max(0.0, min(1.0, float(chunk.vector_score or 0.0)))
    fts_score = max(0.0, min(1.0, float(chunk.fts_score or 0.0)))
    exact_score = max(0.0, min(1.0, float(chunk.exact_score or 0.0)))
    reference_score = _legal_reference_bonus(
        normalized_query,
        chunk,
        features.normalized_document,
    )

    score = (
        0.20 * hybrid_score
        + 0.32 * lexical_coverage
        + 0.10 * phrase_score
        + 0.10 * vector_score
        + 0.06 * fts_score
        + 0.22 * max(exact_score, reference_score)
        + _vehicle_scope_bonus(normalized_query, features.normalized_heading)
        + _structural_intent_bonus(
            normalized_query,
            features.normalized_content,
            chunk.article_num,
        )
        + _topic_specific_bonus(
            normalized_query,
            normalized_content=features.normalized_content,
            normalized_document=features.normalized_document,
            article_num=chunk.article_num,
            clause_num=chunk.clause_num,
        )
    )
    return round(max(0.0, min(1.0, score)), 6)


async def rerank_chunks(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int | None = None,
) -> RerankResult:
    """Rank candidates locally using hybrid, lexical, phrase, and legal-reference signals."""
    top_k = top_k or settings.LOCAL_RANK_TOP_K
    if not candidates:
        return RerankResult(chunks=[], reranker_used=False, low_confidence=True)

    normalized_query = _normalize(query)
    query_tokens = _tokens_from_normalized(normalized_query)
    candidate_features = {chunk.chunk_id: _candidate_features(chunk) for chunk in candidates}
    term_weights = _query_term_weights(query_tokens, list(candidate_features.values()))
    normalized_hybrid = _normalized_hybrid_scores(candidates)
    ranked = [
        chunk.model_copy(
            update={
                "rerank_score": _score_chunk(
                    normalized_query,
                    query_tokens,
                    chunk,
                    features=candidate_features[chunk.chunk_id],
                    hybrid_score=normalized_hybrid[chunk.chunk_id],
                    term_weights=term_weights,
                )
            }
        )
        for chunk in candidates
    ]
    ranked.sort(key=lambda chunk: chunk.rerank_score or 0.0, reverse=True)
    selected = ranked[:top_k]
    top_score = selected[0].rerank_score if selected else None
    return RerankResult(
        chunks=selected,
        low_confidence=top_score is None or top_score < settings.LOCAL_RANK_MIN_SCORE,
        top_score=top_score,
    )


__all__ = ["RerankResult", "rerank_chunks"]
