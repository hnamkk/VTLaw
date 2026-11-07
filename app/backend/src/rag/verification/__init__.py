"""Citation verification pipeline (spec 12).

Verifies that legal claims in an LLM-generated answer are grounded in
the retrieved context chunks. Assigns verification status to each citation.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import date

from src.rag.verification.replacement import find_replacement
from src.schemas.rag import Citation, RetrievedChunk, VerificationStatus

logger = logging.getLogger(__name__)

_DIEU_PATTERN = re.compile(r"[Đđ]iều\s+(\d+)", re.IGNORECASE)
_KHOAN_PATTERN = re.compile(r"[Kk]hoản\s+(\d+)", re.IGNORECASE)
_DIEM_PATTERN = re.compile(r"[Đđ]iểm\s+([a-zđ])", re.IGNORECASE)
# Reverse-order pattern: "khoản X [điểm Y] Điều Z" (clause-first form common
# in Vietnamese legal text, e.g. "khoản 2 Điều 5").
_REVERSE_REF_PATTERN = re.compile(
    r"[Kk]hoản\s+(\d+)"
    r"(?:\s*,?\s*[Đđ]iểm\s+([a-zđ]))?"
    r"\s*,?\s*[Đđ]iều\s+(\d+)",
    re.IGNORECASE,
)

# Lookahead distance in chars after a Điều match to search for Khoản/Điểm.
# LLM may insert verbose explanation between them (e.g. "Điều 5, trong đó
# quy định cụ thể tại khoản 2"), so use generous windows.
_KHOAN_LOOKAHEAD = 250
_DIEM_LOOKAHEAD = 80
_CLAIM_BOUNDARY_PATTERN = re.compile(r"\r?\n|;|[!?]|(?<!\d)\.(?!\d)|[\u2022\u25cf\u25aa]")


def _extract_article_refs(text: str) -> list[dict]:
    """Extract legal references (Điều/Khoản/Điểm) from generated text.

    Handles both canonical order ("Điều X, khoản Y, điểm Z") and reverse
    order ("khoản Y điểm Z Điều X") commonly found in Vietnamese legal text.
    """
    refs: list[dict] = []
    consumed_spans: list[tuple[int, int]] = []

    # Pass 1: reverse-order refs ("khoản 2 Điều 5") — extract first so
    # pass 2 skips Điều matches already covered by a reverse ref.
    for match in _REVERSE_REF_PATTERN.finditer(text):
        refs.append(
            {
                "article_num": int(match.group(3)),
                "clause_num": int(match.group(1)),
                "point_num": match.group(2),
                "start": match.start(),
                "end": match.end(),
            }
        )
        consumed_spans.append((match.start(), match.end()))

    def _in_consumed(pos: int) -> bool:
        return any(s <= pos < e for s, e in consumed_spans)

    # Pass 2: canonical order ("Điều X … khoản Y … điểm Z")
    for match in _DIEU_PATTERN.finditer(text):
        if _in_consumed(match.start()):
            continue
        ref: dict = {
            "article_num": int(match.group(1)),
            "clause_num": None,
            "point_num": None,
            "start": match.start(),
            "end": match.end(),
        }
        after = text[match.end() : match.end() + _KHOAN_LOOKAHEAD]
        # Stop at a sentence/bullet boundary or another Điều reference. A
        # Khoản in the next bullet belongs to that citation, not this one.
        boundary = _CLAIM_BOUNDARY_PATTERN.search(after)
        next_dieu = _DIEU_PATTERN.search(after)
        cut_positions = [match.start() for match in (boundary, next_dieu) if match is not None]
        if cut_positions:
            after = after[: min(cut_positions)]
        clause_m = _KHOAN_PATTERN.search(after)
        if clause_m:
            ref["clause_num"] = int(clause_m.group(1))
            after_clause = after[clause_m.end() : clause_m.end() + _DIEM_LOOKAHEAD]
            point_m = _DIEM_PATTERN.search(after_clause)
            if point_m:
                ref["point_num"] = point_m.group(1)
        refs.append(ref)
    refs.sort(key=lambda item: int(item["start"]))
    return refs


def _find_best_chunk(
    ref: dict,
    context_chunks: list[RetrievedChunk],
    claim_text: str = "",
) -> RetrievedChunk | None:
    """Find the best matching chunk for an article/clause reference.

    Preference order:
    1. Exact article + clause + point match.
    2. Article + clause where the chunk is the whole clause (point_num=None) —
       a clause-level chunk genuinely contains all its points, so it supports a
       point-level citation.
    3. An article-level chunk when the answer cites only the article.
    """
    normalized_claim = _normalize_reference_text(claim_text)

    def match_tier(chunk: RetrievedChunk) -> int:
        if chunk.article_num != ref["article_num"]:
            return 0
        if ref["clause_num"] is not None and chunk.clause_num != ref["clause_num"]:
            return 0
        if ref["point_num"] is None:
            return 3
        if chunk.point_num == ref["point_num"]:
            return 3
        if chunk.point_num is None:
            return 2
        return 0

    def document_mention(chunk: RetrievedChunk) -> int:
        if not normalized_claim:
            return 0
        number = _normalize_reference_text(chunk.document_number or "")
        title = _normalize_reference_text(chunk.doc_title)
        if number and number in normalized_claim:
            return 2
        if title and len(title) >= 8 and title in normalized_claim:
            return 1
        return 0

    candidates = [chunk for chunk in context_chunks if match_tier(chunk) > 0]
    explicit_numbers = set(re.findall(r"\b\d{1,4}/(?:\d{4}/)?[a-z][a-z0-9/ ]*", normalized_claim))
    if explicit_numbers:
        # Match the actual document identity, not just a reused article number.
        candidates = [chunk for chunk in candidates if document_mention(chunk) > 0]
    elif len({chunk.doc_id for chunk in candidates}) > 1:
        return None
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda chunk: (
            match_tier(chunk),
            document_mention(chunk),
            float(chunk.rerank_score or chunk.hybrid_score or 0.0),
        ),
    )


def _normalize_reference_text(text: str) -> str:
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    normalized = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9/]+", " ", normalized).strip()


def _contains_internal_reference(chunk: RetrievedChunk, ref: dict) -> bool:
    """Check whether a source quotes a locator as an internal cross-reference."""
    text = _normalize_reference_text(chunk.full_text or chunk.text_snippet)
    article = int(ref["article_num"])
    clause = ref.get("clause_num")
    if clause is None:
        return f"dieu {article}" in text
    return f"khoan {int(clause)} dieu {article}" in text or bool(
        re.search(
            rf"dieu\s+{article}\b.{{0,120}}\bkhoan\s+{int(clause)}\b",
            text,
        )
    )


_GROUNDING_STOP_WORDS = {
    "cac",
    "cho",
    "co",
    "cua",
    "can",
    "cong",
    "cu",
    "dinh",
    "dieu",
    "diem",
    "duoc",
    "khoan",
    "khong",
    "la",
    "luat",
    "mot",
    "nghi",
    "quy",
    "theo",
    "thi",
    "thong",
    "tu",
    "va",
    "van",
    "voi",
}


def _grounding_tokens(text: str) -> set[str]:
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    normalized = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 1 and token not in _GROUNDING_STOP_WORDS
    }


def _claim_segment(answer: str, ref: dict) -> str:
    """Return the sentence or bullet containing a legal reference."""
    start = int(ref.get("start", 0))
    end = int(ref.get("end", start))
    boundaries = list(_CLAIM_BOUNDARY_PATTERN.finditer(answer))
    left_candidates = [match.end() for match in boundaries if match.end() <= start]
    left = max(left_candidates, default=0)
    right_candidates = [match.start() for match in boundaries if match.start() >= end]
    right = min(right_candidates, default=len(answer))
    segment = answer[left:right].strip()
    normalized_segment = _normalize_reference_text(segment)
    source_only = any(
        phrase in f" {normalized_segment} "
        for phrase in (" can cu ", " can cu phap ly ", " cu the theo ", " theo ")
    )
    source_only = source_only or (segment.startswith("[") and "|" in segment)
    if left > 0 and source_only:
        prefix = answer[:left].rstrip(" \n\r\t.;")
        previous_boundaries = list(_CLAIM_BOUNDARY_PATTERN.finditer(prefix))
        previous_left = max((match.end() for match in previous_boundaries), default=0)
        previous_segment = prefix[previous_left:].strip()
        if previous_segment:
            segment = f"{previous_segment} {segment}"
    return segment


def _snippet_grounded(answer_segment: str, chunk_text: str) -> float:
    """Measure meaningful claim-token coverage in source text."""
    answer_words = _grounding_tokens(answer_segment)
    chunk_words = _grounding_tokens(chunk_text)
    if not answer_words:
        return 0.0
    overlap = answer_words & chunk_words
    return len(overlap) / len(answer_words)


def _numeric_claim_grounded(answer_segment: str, chunk_text: str) -> bool:
    """Require every substantive number in a claim to occur in its source."""
    cleaned = _DIEU_PATTERN.sub(" ", answer_segment)
    cleaned = _KHOAN_PATTERN.sub(" ", cleaned)
    cleaned = _DIEM_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(r"\b\d{1,4}/\d{4}(?:/[A-ZĐ-]+)?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b\d{1,4}/(?=[A-Z0-9Đ-]*[A-ZĐ])[A-Z0-9Đ-]+(?:/[A-Z0-9Đ-]+)*\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    def numbers(text: str) -> set[str]:
        normalized_numbers: set[str] = set()
        for value in re.findall(r"\b\d[\d.,]*\b", text):
            digits = re.sub(r"\D", "", value)
            if digits:
                normalized_numbers.add(str(int(digits)))
        return normalized_numbers

    return numbers(cleaned).issubset(numbers(chunk_text))


def _compute_confidence(
    chunk: RetrievedChunk,
    ref: dict,
    claim_text: str,
) -> tuple[VerificationStatus, float]:
    """Determine verification status and confidence for a citation."""
    article_match = chunk.article_num == ref["article_num"]
    clause_match = ref["clause_num"] is None or chunk.clause_num == ref["clause_num"]
    # A clause-level chunk (point_num=None) contains all of its points, so it
    # fully supports a point-level citation — not just a partial match.
    point_match = (
        ref["point_num"] is None or chunk.point_num == ref["point_num"] or chunk.point_num is None
    )

    if chunk.status != "active":
        return VerificationStatus.blocked, 0.0

    grounding = _snippet_grounded(claim_text, chunk.full_text or chunk.text_snippet)
    numeric_grounded = _numeric_claim_grounded(claim_text, chunk.full_text or chunk.text_snippet)

    if article_match and clause_match and point_match and numeric_grounded and grounding >= 0.25:
        return VerificationStatus.verified, min(0.98, 0.72 + grounding * 0.28)

    if article_match and clause_match and numeric_grounded and grounding >= 0.15:
        return VerificationStatus.partial, min(0.78, 0.42 + grounding * 0.32)

    return VerificationStatus.unverified, max(0.1, grounding * 0.5)


def verify_citations(
    answer: str,
    context_chunks: list[RetrievedChunk],
) -> list[Citation]:
    """Extract claims from answer and verify against context chunks.

    Returns a list of Citation objects with verification status.
    """
    refs = _extract_article_refs(answer)
    citations: list[Citation] = []
    seen_chunks: set[str] = set()
    seen_doc_ids: set[str] = set()

    for ref in refs:
        claim_text = _claim_segment(answer, ref)
        chunk = _find_best_chunk(ref, context_chunks, claim_text)
        if chunk is None:
            # A model may faithfully repeat an internal cross-reference from an
            # already cited source. Do not misreport that locator as a separate,
            # independently retrieved citation.
            if any(
                candidate.chunk_id in seen_chunks and _contains_internal_reference(candidate, ref)
                for candidate in context_chunks
            ):
                continue
            citations.append(
                Citation(
                    citation_id=str(uuid.uuid4()),
                    chunk_id="",
                    doc_id="",
                    doc_title="",
                    doc_type="",
                    status="",
                    effective_date=(
                        context_chunks[0].effective_date if context_chunks else date.today()
                    ),
                    article_num=ref["article_num"],
                    clause_num=ref["clause_num"],
                    point_num=ref["point_num"],
                    source_url=None,
                    text_snippet="",
                    verification_status=VerificationStatus.unverified,
                    confidence=0.0,
                )
            )
            continue

        # Verify every claim, including repeated references to the same source.
        seen_chunks.add(chunk.chunk_id)
        seen_doc_ids.add(chunk.doc_id)

        status, confidence = _compute_confidence(chunk, ref, claim_text)
        citations.append(
            Citation(
                citation_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                doc_type=chunk.doc_type,
                status=chunk.status,
                effective_date=chunk.effective_date,
                article_num=ref["article_num"],
                clause_num=ref["clause_num"],
                point_num=ref["point_num"],
                locator_type=chunk.locator_type,
                locator_label=chunk.locator_label,
                section_path=chunk.section_path,
                section_number=chunk.section_number,
                sign_code=chunk.sign_codes[0] if len(chunk.sign_codes) == 1 else None,
                asset_ids=chunk.asset_ids,
                source_url=chunk.source_url,
                text_snippet=chunk.text_snippet[:200],
                verification_status=status,
                confidence=confidence,
            )
        )

    # Exact technical locator fallback for QCVN sign-code claims.
    answer_sign_codes = {
        f"{prefix.upper()}.{number.lower()}"
        for prefix, number in re.findall(
            r"\b([PWRIS])[\s.-]?(\d{2,3}[a-z]?)\b", answer, re.IGNORECASE
        )
    }
    for chunk in context_chunks:
        if chunk.chunk_id in seen_chunks:
            continue
        matching_codes = answer_sign_codes.intersection(chunk.sign_codes)
        if not matching_codes:
            continue
        sign_code = sorted(matching_codes)[0]
        citations.append(
            Citation(
                citation_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                doc_type=chunk.doc_type,
                status=chunk.status,
                effective_date=chunk.effective_date,
                locator_type=chunk.locator_type or "sign_code",
                locator_label=chunk.locator_label,
                section_path=chunk.section_path,
                section_number=chunk.section_number,
                sign_code=sign_code,
                asset_ids=chunk.asset_ids,
                source_url=chunk.source_url,
                text_snippet=chunk.text_snippet[:200],
                verification_status=(
                    VerificationStatus.verified
                    if chunk.status == "active"
                    and _numeric_claim_grounded(answer, chunk.full_text or chunk.text_snippet)
                    and _snippet_grounded(answer, chunk.full_text or chunk.text_snippet) >= 0.5
                    else VerificationStatus.unverified
                ),
                confidence=0.8,
            )
        )
        seen_chunks.add(chunk.chunk_id)
        seen_doc_ids.add(chunk.doc_id)

    return citations


def citations_from_retrieval_units(
    context_chunks: list[RetrievedChunk],
    *,
    max_citations: int = 3,
) -> list[Citation]:
    """Create structured citations directly from active retrieval units.

    This fallback is used when an answer is grounded in retrieved KB units but
    the model failed to spell out Điều/Khoản in a parseable way. It never invents
    legal locators; every field comes from the retrieved unit metadata.
    """
    citations: list[Citation] = []
    seen_chunk_ids: set[str] = set()
    ordered_chunks = context_chunks
    for chunk in ordered_chunks:
        if len(citations) >= max_citations:
            break
        if chunk.status != "active" or not chunk.doc_id or not chunk.chunk_id:
            continue
        if chunk.chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk.chunk_id)
        citations.append(
            Citation(
                citation_id=str(uuid.uuid4()),
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                doc_type=chunk.doc_type,
                status=chunk.status,
                effective_date=chunk.effective_date,
                article_num=chunk.article_num,
                clause_num=chunk.clause_num,
                point_num=chunk.point_num,
                locator_type=chunk.locator_type,
                locator_label=chunk.locator_label,
                section_path=chunk.section_path,
                section_number=chunk.section_number,
                sign_code=chunk.sign_codes[0] if len(chunk.sign_codes) == 1 else None,
                asset_ids=chunk.asset_ids,
                source_url=chunk.source_url,
                text_snippet=chunk.text_snippet[:200],
                verification_status=VerificationStatus.verified,
                confidence=0.82,
            )
        )
    return citations


def has_hallucination(citations: list[Citation]) -> bool:
    """Treat every unsupported legal locator as a hallucination."""
    blocked = sum(1 for c in citations if c.verification_status == VerificationStatus.blocked)
    unverified = sum(1 for c in citations if c.verification_status == VerificationStatus.unverified)
    return blocked > 0 or unverified > 0


def prune_unsupported_cited_lines(answer: str, context_chunks: list[RetrievedChunk]) -> str:
    """Remove complete answer lines that contain an unsupported legal locator.

    Generation commonly places each supporting proposition in its own bullet. Keeping
    verified bullets while dropping a tangential, miscited bullet is safer than either
    exposing the bad claim or discarding the entire grounded answer.
    """
    retained: list[str] = []
    for line in answer.splitlines():
        if not _extract_article_refs(line):
            retained.append(line)
            continue
        line_citations = verify_citations(line, context_chunks)
        if line_citations and has_hallucination(line_citations):
            continue
        retained.append(line)

    return "\n".join(retained).strip()


def compute_faithfulness_score(citations: list[Citation]) -> float:
    """Compute overall faithfulness score from citation verification results."""
    if not citations:
        return 0.0
    weights = {
        VerificationStatus.verified: 1.0,
        VerificationStatus.partial: 0.6,
        VerificationStatus.unverified: 0.1,
        VerificationStatus.blocked: 0.0,
    }
    total = sum(weights[c.verification_status] for c in citations)
    return total / len(citations)


__all__ = [
    "compute_faithfulness_score",
    "citations_from_retrieval_units",
    "find_replacement",
    "has_hallucination",
    "prune_unsupported_cited_lines",
    "verify_citations",
]
