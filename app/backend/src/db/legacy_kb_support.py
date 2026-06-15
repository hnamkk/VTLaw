"""Legacy KB helpers retained only for old-data maintenance scripts.

These helpers operate on the pre-cutover ``LegalDocument`` / ``KbUpdateQueue``
schema but are isolated from HTTP runtime modules so current chat/public/admin
paths do not import legacy route code.
"""

from __future__ import annotations

from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument
from src.rag.metadata_extraction import build_canonical_title, infer_document_number_from_filename


def reconcile_legacy_document_metadata(document: LegalDocument, queue: KbUpdateQueue) -> None:
    """Backfill canonical metadata from upload-derived candidates before publish."""
    metadata = dict(queue.extracted_metadata or {})
    document_number = (
        document.document_number
        or metadata.get("document_number_candidate")
        or infer_document_number_from_filename(queue.source_file_name or "")
    )
    if document_number:
        if not document.document_number:
            document.document_number = str(document_number)
        if document.document_number not in document.title:
            document.title = build_canonical_title(
                document.doc_type,
                document.document_number,
                document.title,
            )


__all__ = ["reconcile_legacy_document_metadata"]
