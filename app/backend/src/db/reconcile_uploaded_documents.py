"""Legacy repair utility for pre-cutover uploads.

This script targets the old ``LegalDocument`` / ``document_chunks`` schema and
is intentionally kept out of the current runtime. Use only for legacy data
maintenance with an explicit opt-in.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.legacy_kb_support import reconcile_legacy_document_metadata
from src.db.session import async_session_factory
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument

sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class RepairStats:
    queues_seen: int = 0
    documents_updated: int = 0
    chunks_updated: int = 0


def _is_uploaded_queue(queue: KbUpdateQueue) -> bool:
    source_path = (queue.source_path or "").lower()
    source_file_name = (queue.source_file_name or "").lower()
    return "storage\\uploads\\" in source_path or source_file_name.endswith((".docx", ".pdf"))


def _target_status(document: LegalDocument, queue: KbUpdateQueue) -> tuple[str, str]:
    if queue.change_type == "repeal":
        return "repealed", "repealed"
    if document.valid_from and document.valid_from > date.today():
        return "pending_review", "future_effective"
    return "active", document.legal_status or "active"


async def reconcile(confirm: bool) -> int:
    stats = RepairStats()
    async with async_session_factory() as session:
        queues = (
            await session.execute(
                select(KbUpdateQueue)
                .where(KbUpdateQueue.review_status == "approved")
                .options(selectinload(KbUpdateQueue.document).selectinload(LegalDocument.chunks))
                .order_by(KbUpdateQueue.created_at.asc())
            )
        ).scalars().all()

        for queue in queues:
            if queue.document is None or not _is_uploaded_queue(queue):
                continue
            stats.queues_seen += 1
            document = queue.document
            before_doc = (
                document.document_number,
                document.title,
                document.status,
                document.legal_status,
            )
            reconcile_legacy_document_metadata(document, queue)
            target_status, target_legal_status = _target_status(document, queue)
            document.review_status = "approved"
            document.status = target_status
            document.legal_status = target_legal_status

            updated_chunk_count = 0
            for chunk in document.chunks:
                expected_status = document.status
                expected_provision_status = (
                    "repealed"
                    if document.status == "repealed"
                    else "future_effective"
                    if document.legal_status == "future_effective"
                    else "active"
                )
                if (
                    chunk.status != expected_status
                    or chunk.provision_status != expected_provision_status
                    or chunk.effective_date != document.effective_date
                    or chunk.valid_from != (document.valid_from or document.effective_date)
                    or chunk.valid_to != (document.valid_to or document.expiry_date)
                    or chunk.rag_enabled != document.rag_enabled
                ):
                    chunk.status = expected_status
                    chunk.provision_status = expected_provision_status
                    chunk.effective_date = document.effective_date
                    chunk.valid_from = document.valid_from or document.effective_date
                    chunk.valid_to = document.valid_to or document.expiry_date
                    chunk.rag_enabled = document.rag_enabled
                    updated_chunk_count += 1

            after_doc = (
                document.document_number,
                document.title,
                document.status,
                document.legal_status,
            )
            if before_doc != after_doc or updated_chunk_count:
                stats.documents_updated += 1
                stats.chunks_updated += updated_chunk_count
                print(
                    f"REPAIR: {document.doc_id} | {before_doc} -> {after_doc} | chunks={updated_chunk_count}"
                )

        if not confirm:
            print(
                f"DRY-RUN: queues={stats.queues_seen}, documents={stats.documents_updated}, "
                f"chunks={stats.chunks_updated}"
            )
            await session.rollback()
            return 0

        await session.commit()
        print(
            f"COMMIT: queues={stats.queues_seen}, documents={stats.documents_updated}, "
            f"chunks={stats.chunks_updated}"
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--legacy-allow",
        action="store_true",
        help="Acknowledge this script operates on legacy KB data only.",
    )
    args = parser.parse_args()
    if not args.legacy_allow:
        raise SystemExit(
            "Legacy script blocked by default. Re-run with --legacy-allow to maintain old KB data."
        )
    raise SystemExit(asyncio.run(reconcile(args.confirm)))


if __name__ == "__main__":
    main()
