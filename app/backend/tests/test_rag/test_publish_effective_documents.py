from datetime import date

from src.db.publish_effective_documents import (
    _has_approved_queue,
    _publish_document,
    _queue_matches_document_version,
)
from src.models.document_chunk import DocumentChunk
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument


def test_has_approved_queue_requires_approved_review_status():
    document = LegalDocument(
        doc_id="doc-1",
        title="Luat 118/2025/QH15",
        doc_type="LUAT",
        status="pending_review",
        review_status="approved",
        legal_status="future_effective",
        effective_date=date(2026, 7, 1),
        valid_from=date(2026, 7, 1),
        issuer="Quoc hoi",
        domain_tags=[],
        queue_items=[
            KbUpdateQueue(
                queue_id="queue-1",
                doc_id="doc-1",
                change_type="create",
                review_status="approved",
                processing_status="ready",
            )
        ],
    )

    assert _has_approved_queue(document) is True


def test_has_approved_queue_rejects_update_queue_for_future_publish():
    document = LegalDocument(
        doc_id="doc-1",
        title="Luat 118/2025/QH15",
        doc_type="LUAT",
        status="pending_review",
        review_status="approved",
        legal_status="future_effective",
        effective_date=date(2026, 7, 1),
        valid_from=date(2026, 7, 1),
        issuer="Quoc hoi",
        domain_tags=[],
        queue_items=[
            KbUpdateQueue(
                queue_id="queue-1",
                doc_id="doc-1",
                change_type="update",
                review_status="approved",
                processing_status="ready",
            )
        ],
    )

    assert _has_approved_queue(document) is False


def test_queue_version_match_rejects_checksum_mismatch():
    document = LegalDocument(
        doc_id="doc-1",
        title="Luat 118/2025/QH15",
        doc_type="LUAT",
        status="pending_review",
        review_status="approved",
        legal_status="future_effective",
        effective_date=date(2026, 7, 1),
        valid_from=date(2026, 7, 1),
        issuer="Quoc hoi",
        domain_tags=[],
        source_checksum="document-checksum",
    )
    queue = KbUpdateQueue(
        queue_id="queue-1",
        doc_id="doc-1",
        change_type="create",
        review_status="approved",
        processing_status="ready",
        extracted_metadata={"source_checksum": "queue-checksum"},
    )

    assert _queue_matches_document_version(document, queue) is False


def test_publish_document_activates_document_and_chunks():
    document = LegalDocument(
        doc_id="doc-1",
        title="Luat 118/2025/QH15",
        doc_type="LUAT",
        status="pending_review",
        review_status="approved",
        legal_status="future_effective",
        effective_date=date(2026, 7, 1),
        valid_from=date(2026, 7, 1),
        issuer="Quoc hoi",
        domain_tags=[],
        chunks=[
            DocumentChunk(
                chunk_id="chunk-1",
                doc_id="doc-1",
                text_content="Noi dung Dieu 1",
                chunk_type="dieu",
                article_num=1,
                status="pending_review",
                effective_date=date(2026, 7, 1),
                valid_from=date(2026, 7, 1),
                provision_status="future_effective",
                metadata_json={},
            )
        ],
    )

    updated_chunks = _publish_document(document, date(2026, 7, 1))

    assert updated_chunks == 1
    assert document.status == "active"
    assert document.legal_status == "active"
    assert document.chunks[0].status == "active"
    assert document.chunks[0].provision_status == "active"
