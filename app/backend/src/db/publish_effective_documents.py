"""Legacy publish utility for pre-cutover documents.

This script only operates on the old ``LegalDocument`` / ``document_chunks``
tables and is not part of the current KB runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.session import async_session_factory
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument

sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class PublishEffectiveStats:
    documents_seen: int = 0
    documents_published: int = 0
    chunks_published: int = 0


def _queue_source_checksum(queue: KbUpdateQueue) -> str | None:
    checksum = (queue.extracted_metadata or {}).get("source_checksum")
    return checksum if isinstance(checksum, str) and checksum else None


def _queue_matches_document_version(document: LegalDocument, queue: KbUpdateQueue) -> bool:
    if queue.review_status != "approved":
        return False
    if queue.processing_status != "ready":
        return False
    if queue.change_type != "create":
        return False
    if queue.doc_id != document.doc_id:
        return False
    queue_checksum = _queue_source_checksum(queue)
    if queue_checksum and document.source_checksum and queue_checksum != document.source_checksum:
        return False
    return True


def _has_approved_queue(document: LegalDocument) -> bool:
    return any(
        _queue_matches_document_version(document, queue) for queue in document.queue_items
    )


def _publish_document(document: LegalDocument, today: date) -> int:
    document.status = "active"
    document.legal_status = "active"
    document.review_status = "approved"
    document.valid_from = document.valid_from or document.effective_date
    document.valid_to = document.valid_to or document.expiry_date

    updated_chunks = 0
    for chunk in document.chunks:
        if chunk.doc_id != document.doc_id:
            continue
        if chunk.status == "repealed" or chunk.provision_status == "repealed":
            continue
        if (
            chunk.status != "active"
            or chunk.provision_status != "active"
            or chunk.valid_from != (document.valid_from or document.effective_date)
            or chunk.valid_to != (document.valid_to or document.expiry_date)
        ):
            updated_chunks += 1
        chunk.status = "active"
        chunk.provision_status = "active"
        chunk.effective_date = document.effective_date
        chunk.valid_from = document.valid_from or document.effective_date
        chunk.valid_to = document.valid_to or document.expiry_date
        chunk.rag_enabled = document.rag_enabled
    return updated_chunks


async def publish_effective_documents(
    *,
    confirm: bool,
    today: date | None = None,
) -> PublishEffectiveStats:
    """Activate approved future-effective documents whose valid_from is today or earlier."""
    today = today or date.today()
    stats = PublishEffectiveStats()
    async with async_session_factory() as session:
        documents = (
            await session.execute(
                select(LegalDocument)
                .where(
                    LegalDocument.review_status == "approved",
                    LegalDocument.legal_status == "future_effective",
                    LegalDocument.valid_from <= today,
                )
                .options(
                    selectinload(LegalDocument.chunks),
                    selectinload(LegalDocument.queue_items),
                )
                .order_by(LegalDocument.valid_from.asc(), LegalDocument.created_at.asc())
            )
        ).scalars().all()

        stats.documents_seen = len(documents)
        for document in documents:
            if document.status != "pending_review" or not _has_approved_queue(document):
                continue
            chunk_count = _publish_document(document, today)
            stats.documents_published += 1
            stats.chunks_published += chunk_count
            print(
                "PUBLISH: "
                f"{document.doc_id} | {document.document_number or document.title} | "
                f"valid_from={document.valid_from} | chunks={chunk_count}"
            )

        if confirm:
            await session.commit()
            print(
                "COMMIT: "
                f"seen={stats.documents_seen}, documents={stats.documents_published}, "
                f"chunks={stats.chunks_published}"
            )
        else:
            await session.rollback()
            print(
                "DRY-RUN: "
                f"seen={stats.documents_seen}, documents={stats.documents_published}, "
                f"chunks={stats.chunks_published}"
            )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--legacy-allow",
        action="store_true",
        help="Acknowledge this script operates on legacy KB data only.",
    )
    parser.add_argument(
        "--today",
        type=date.fromisoformat,
        default=None,
        help="Override current date as YYYY-MM-DD for release drills.",
    )
    args = parser.parse_args()
    if not args.legacy_allow:
        raise SystemExit(
            "Legacy script blocked by default. Re-run with --legacy-allow to maintain old KB data."
        )
    asyncio.run(publish_effective_documents(confirm=args.confirm, today=args.today))


if __name__ == "__main__":
    main()
