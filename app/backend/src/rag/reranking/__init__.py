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
