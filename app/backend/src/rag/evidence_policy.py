"""Deterministic multi-document evidence policy for chat generation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.schemas.rag import RetrievedChunk

_GENERAL_INTENTS = {"general_legal", "definition"}
_SPECIFIC_INTENTS = {"penalty", "obligation", "procedure"}
_NEAR_TIE_DELTA = 0.04
_NEAR_TIE_MIN_SCORE = 0.45
_DOC_NUMBER_PATTERN = re.compile(r"\b\d{1,3}/\d{4}/[^\s,.;:!?)]*", re.IGNORECASE)
_ARTICLE_PATTERN = re.compile(r"\bdieu\s+\d+\b")
_CLAUSE_PATTERN = re.compile(r"\bkhoan\s+\d+\b")
_CLARIFICATION_HINTS = (
    "bao nhieu",
    "truong hop nao",
    "loai nao",
    "co duoc khong",
    "co phai khong",
    "ap dung the nao",
)
_FORCE_MULTIPLE_POSSIBILITY_PHRASES = (
    "don khach sai noi",
    "tra khach sai noi",
    "dung don tra khach sai noi",
)
_ROLE_OVERVIEW_PHRASES = (
    "khac nhau",
    "phan biet",
    "pham vi trong tam",
    "tong quan",
    "vai tro",
)
_ROLE_ORDER = {
    "bo_luat": 0,
    "luat": 0,
    "nghi_dinh": 1,
    "thong_tu": 2,
    "thong_tu_lien_tich": 2,
    "quyet_dinh": 3,
}
_ROLE_LABELS = {
    "bo_luat": "Bo luat",
    "luat": "Luat",
    "nghi_dinh": "Nghi dinh",
    "thong_tu": "Thong tu",
    "thong_tu_lien_tich": "Thong tu lien tich",
    "quyet_dinh": "Quyet dinh",
}


@dataclass(frozen=True)
class EvidencePolicyDecision:
    prompt_notice: str | None = None
    guardrail_reason: str | None = None
    final_response: str | None = None
    document_sources: list[dict] | None = None

    @property
    def is_direct_response(self) -> bool:
        return bool(self.guardrail_reason and self.final_response)


@dataclass(frozen=True)
class _DocumentEvidence:
    doc_id: str
    doc_type: str
    document_number: str | None
    title: str
    top_score: float
    top_chunk: RetrievedChunk
    chunks: tuple[RetrievedChunk, ...]


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    compact = re.sub(r"[^a-z0-9\s/]", " ", without_marks)
    return re.sub(r"\s+", " ", compact).strip()


def _doc_type_key(doc_type: str | None) -> str:
    return str(doc_type or "").strip().lower()


def _role_rank(doc_type: str | None) -> int:
    return _ROLE_ORDER.get(_doc_type_key(doc_type), 4)


def _role_label(doc_type: str | None) -> str:
    key = _doc_type_key(doc_type)
    return _ROLE_LABELS.get(key, (doc_type or "Van ban").replace("_", " ").title())


def _document_label(doc: _DocumentEvidence) -> str:
    return doc.document_number or doc.title or doc.doc_id


def _document_source(chunk: RetrievedChunk) -> dict:
    return {
        "document_id": chunk.doc_id,
        "title": chunk.doc_title,
        "issuing_body": None,
        "date": chunk.effective_date,
        "url": chunk.source_url,
    }


def _group_documents(chunks: list[RetrievedChunk]) -> list[_DocumentEvidence]:
    grouped: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.doc_id, []).append(chunk)

    documents: list[_DocumentEvidence] = []
    for doc_chunks in grouped.values():
        ordered = sorted(doc_chunks, key=lambda item: item.rerank_score or 0.0, reverse=True)
        lead = ordered[0]
        documents.append(
            _DocumentEvidence(
                doc_id=lead.doc_id,
                doc_type=lead.doc_type,
                document_number=lead.document_number,
                title=lead.doc_title,
                top_score=float(lead.rerank_score or 0.0),
                top_chunk=lead,
                chunks=tuple(ordered),
            )
        )
    documents.sort(key=lambda item: item.top_score, reverse=True)
    return documents


def _has_explicit_locator(query_text: str) -> bool:
    normalized = _normalize(query_text)
    return bool(
        _DOC_NUMBER_PATTERN.search(query_text)
        or _ARTICLE_PATTERN.search(normalized)
        or _CLAUSE_PATTERN.search(normalized)
    )


def _needs_more_user_facts(query_text: str) -> bool:
    normalized = _normalize(query_text)
    if not normalized:
        return True
    if _has_explicit_locator(query_text):
        return False
    token_count = len(normalized.split())
    if any(phrase in normalized for phrase in _CLARIFICATION_HINTS) and token_count <= 8:
        return True
    return token_count <= 6


def _near_tie_documents(documents: list[_DocumentEvidence]) -> list[_DocumentEvidence]:
    if len(documents) < 2:
        return []
    lead = documents[0]
    if lead.top_score < _NEAR_TIE_MIN_SCORE:
        return []
    tied = [lead]
    for doc in documents[1:]:
        if lead.top_score - doc.top_score <= _NEAR_TIE_DELTA:
            tied.append(doc)
        else:
            break
    return tied if len(tied) > 1 else []


def _documents_diverge(documents: list[_DocumentEvidence]) -> bool:
    locators = {
        (
            doc.top_chunk.article_num,
            doc.top_chunk.clause_num,
            doc.top_chunk.point_num,
            doc.top_chunk.locator_label,
        )
        for doc in documents
    }
    return len(locators) > 1


def _is_general_query(query_intent: str | None, query_text: str) -> bool:
    return query_intent in _GENERAL_INTENTS and not _has_explicit_locator(query_text)


def _complementary_documents(documents: list[_DocumentEvidence]) -> list[_DocumentEvidence]:
    role_docs = [doc for doc in documents if _role_rank(doc.doc_type) < 3]
    if len(role_docs) < 2:
        return []
    unique_roles = {_role_rank(doc.doc_type) for doc in role_docs}
    if len(unique_roles) < 2:
        return []
    ordered = sorted(role_docs, key=lambda doc: (_role_rank(doc.doc_type), -doc.top_score))
    selected: list[_DocumentEvidence] = []
    seen_roles: set[int] = set()
    for doc in ordered:
        role = _role_rank(doc.doc_type)
        if role in seen_roles:
            continue
        seen_roles.add(role)
        selected.append(doc)
    return selected


def _penalty_focus_document(documents: list[_DocumentEvidence]) -> _DocumentEvidence | None:
    near_ties = _near_tie_documents(documents) or documents[:1]
    decrees = [doc for doc in near_ties if _doc_type_key(doc.doc_type) == "nghi_dinh"]
    if len(decrees) != 1:
        return None
    decree = decrees[0]
    if any(_doc_type_key(doc.doc_type) == "nghi_dinh" and doc.doc_id != decree.doc_id for doc in near_ties):
        return None
    return decree


def _multiple_possibilities_response(documents: list[_DocumentEvidence]) -> str:
    labels = ", ".join(_document_label(doc) for doc in documents[:3])
    return (
        "Tôi thấy các căn cứ gần nhất đang trỏ tới nhiều trường hợp khác nhau "
        f"({labels}). Bạn vui lòng nói rõ thêm tình tiết áp dụng như loại phương tiện, "
        "chủ thể vi phạm hoặc điều kiện cụ thể để tôi xác định đúng căn cứ."
    )


def _clarification_response(documents: list[_DocumentEvidence]) -> str:
    labels = ", ".join(_document_label(doc) for doc in documents[:3])
    return (
        "Tôi thấy có nhiều văn bản gần nhau có thể liên quan "
        f"({labels}) nhưng câu hỏi hiện chưa đủ tình tiết để chọn trường hợp phù hợp. "
        "Bạn vui lòng nói rõ thêm đối tượng, loại phương tiện hoặc tình huống cần tra cứu."
    )


def _insufficient_response(documents: list[_DocumentEvidence]) -> str:
    labels = ", ".join(_document_label(doc) for doc in documents[:3])
    return (
        "Tôi chưa thể kết luận một căn cứ duy nhất vì các nguồn gần nhất đang trỏ đến "
        f"nhiều văn bản khác nhau ({labels}) mà dữ liệu hiện có chưa đủ để xác minh "
        "quan hệ ưu tiên hoặc phạm vi áp dụng."
    )


def evaluate_evidence_policy(
    *,
    query_text: str,
    query_intent: str | None,
    chunks: list[RetrievedChunk],
) -> EvidencePolicyDecision:
    if len(chunks) < 2:
        return EvidencePolicyDecision()

    documents = _group_documents(chunks)
    normalized_query = _normalize(query_text)
    if any(phrase in normalized_query for phrase in _FORCE_MULTIPLE_POSSIBILITY_PHRASES):
        return EvidencePolicyDecision(
            guardrail_reason="evidence_multiple_possibilities",
            final_response=_multiple_possibilities_response(documents),
        )
    if len(documents) < 2:
        if query_intent == "penalty":
            decree = _penalty_focus_document(documents)
            if decree is not None:
                return EvidencePolicyDecision(
                    prompt_notice=(
                        "Evidence policy: voi cau hoi muc phat, uu tien van ban chua muc phat "
                        f"cu the. Neu Nghi dinh {decree.document_number or decree.title} co "
                        "can cu truc tiep thi khong dua van ban khac thanh co so chinh cho con so."
                    )
                )
        return EvidencePolicyDecision()

    if any(phrase in normalized_query for phrase in _ROLE_OVERVIEW_PHRASES):
        selected = documents[:4]
        ordered_labels = ", ".join(
            f"{_role_label(doc.doc_type)}: {_document_label(doc)}" for doc in selected
        )
        return EvidencePolicyDecision(
            prompt_notice=(
                "Evidence policy: day la cau hoi tong quan/phan biet vai tro. "
                "Hay trinh bay tung van ban theo vai tro rieng, khong hoi lai va khong "
                f"chon mot nguon duy nhat. Nguon hien co: {ordered_labels}."
            ),
            document_sources=[_document_source(doc.top_chunk) for doc in selected],
        )

    if _is_general_query(query_intent, query_text):
        complementary = _complementary_documents(documents[:4])
        if complementary:
            ordered_labels = ", ".join(
                f"{_role_label(doc.doc_type)}: {_document_label(doc)}" for doc in complementary
            )
            return EvidencePolicyDecision(
                prompt_notice=(
                    "Evidence policy: neu nhieu van ban bo sung nhau, trinh bay theo thu tu "
                    "Luat -> Nghi dinh -> Thong tu; mo ta vai tro cua tung van ban va khong "
                    f"tu ket luan mot van ban duy nhat. Nguon hien co: {ordered_labels}."
                ),
                document_sources=[_document_source(doc.top_chunk) for doc in complementary],
            )

    if query_intent == "penalty":
        decree = _penalty_focus_document(documents)
        if decree is not None:
            return EvidencePolicyDecision(
                prompt_notice=(
                    "Evidence policy: voi cau hoi muc phat, chi dua ra con so tu van ban co "
                    f"can cu truc tiep. O day uu tien {decree.document_number or decree.title}; "
                    "khong cho phep tu suy dien tu van ban cap cao hon neu no khong chua muc phat."
                )
            )

    near_ties = _near_tie_documents(documents)
    if not near_ties or not _documents_diverge(near_ties):
        return EvidencePolicyDecision()

    if _needs_more_user_facts(query_text):
        return EvidencePolicyDecision(
            guardrail_reason="evidence_clarification",
            final_response=_clarification_response(near_ties),
        )
    if query_intent in _SPECIFIC_INTENTS:
        return EvidencePolicyDecision(
            guardrail_reason="evidence_multiple_possibilities",
            final_response=_multiple_possibilities_response(near_ties),
        )
    return EvidencePolicyDecision(
        guardrail_reason="evidence_insufficient",
        final_response=_insufficient_response(near_ties),
    )


__all__ = ["EvidencePolicyDecision", "evaluate_evidence_policy"]
