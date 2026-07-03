from datetime import date

from src.kb.lifecycle import apply_current_state, apply_expired_state, is_document_expired
from src.models.document_chunk import DocumentChunk
from src.models.legal_document import LegalDocument


def _document(*, status: str = "active", expiry_date: date | None = None) -> LegalDocument:
    document = LegalDocument(
        doc_id="doc-1",
        title="Thông tư kiểm thử",
        doc_type="THONG_TU",
        status=status,
        review_status="approved",
        legal_status="repealed" if status == "repealed" else "active",
        rag_scope="disabled" if status == "repealed" else "enabled",
        rag_enabled=status == "active",
        effective_date=date(2025, 1, 1),
        expiry_date=expiry_date,
        valid_from=date(2025, 1, 1),
        valid_to=expiry_date,
        issuer="Bộ Xây dựng",
        domain_tags=["road_law"],
    )
    document.chunks = [
        DocumentChunk(
            chunk_id="chunk-1",
            doc_id="doc-1",
            text_content="Điều 1. Nội dung kiểm thử.",
            chunk_type="dieu",
            article_num=1,
            status=status,
            effective_date=date(2025, 1, 1),
            provision_status="repealed" if status == "repealed" else "active",
            rag_enabled=status == "active",
            metadata_json={},
        )
    ]
    return document


def test_expiry_date_is_first_non_searchable_day():
    document = _document(expiry_date=date(2026, 6, 29))

    assert not is_document_expired(document, as_of=date(2026, 6, 28))
    assert is_document_expired(document, as_of=date(2026, 6, 29))


def test_apply_expired_state_disables_document_and_all_chunks():
    document = _document(expiry_date=date(2026, 6, 29))

    apply_expired_state(document, expiry_on=date(2026, 6, 29))

    assert document.status == "repealed"
    assert document.legal_status == "repealed"
    assert document.rag_scope == "disabled"
    assert document.rag_enabled is False
    assert document.chunks[0].status == "repealed"
    assert document.chunks[0].provision_status == "repealed"
    assert document.chunks[0].rag_enabled is False
    assert document.chunks[0].valid_to == date(2026, 6, 29)


def test_metadata_reconciliation_does_not_reactivate_repealed_document():
    document = _document(status="repealed")

    apply_current_state(document, as_of=date(2026, 6, 29))

    assert document.status == "repealed"
    assert document.legal_status == "repealed"
    assert document.rag_enabled is False
    assert document.chunks[0].rag_enabled is False


def test_future_expiry_keeps_approved_document_searchable_until_due_date():
    document = _document(expiry_date=date(2026, 7, 1))

    apply_current_state(document, as_of=date(2026, 6, 29))

    assert document.status == "active"
    assert document.legal_status == "active"
    assert document.rag_enabled is True
    assert document.chunks[0].rag_enabled is True
