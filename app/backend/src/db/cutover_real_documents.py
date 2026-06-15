"""Safely remove demo seed documents after the reviewed corpus is ready."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import func, select

from src.db.seed import SEED_DOC_IDS
from src.db.session import async_session_factory
from src.models.document_chunk import DocumentChunk
from src.models.legal_document import LegalDocument

EXPECTED_REAL_DOCUMENTS = 12


@dataclass(frozen=True)
class CutoverReadiness:
    real_documents: int
    approved_documents: int
    searchable_chunks: int
    embedded_searchable_chunks: int
    seed_documents: int

    @property
    def ready(self) -> bool:
        return (
            self.real_documents == EXPECTED_REAL_DOCUMENTS
            and self.approved_documents == EXPECTED_REAL_DOCUMENTS
            and self.searchable_chunks > 0
            and self.searchable_chunks == self.embedded_searchable_chunks
        )


async def inspect_readiness() -> CutoverReadiness:
    async with async_session_factory() as session:
        real_filter = LegalDocument.source_checksum.is_not(None)
        approved_filter = (
            real_filter,
            LegalDocument.review_status == "approved",
            LegalDocument.status.in_(("active", "repealed")),
        )
        searchable_filter = (
            LegalDocument.source_checksum.is_not(None),
            DocumentChunk.status == "active",
            DocumentChunk.rag_enabled.is_(True),
        )
        return CutoverReadiness(
            real_documents=await session.scalar(
                select(func.count()).select_from(LegalDocument).where(real_filter)
            )
            or 0,
            approved_documents=await session.scalar(
                select(func.count()).select_from(LegalDocument).where(*approved_filter)
            )
            or 0,
            searchable_chunks=await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(LegalDocument, LegalDocument.doc_id == DocumentChunk.doc_id)
                .where(*searchable_filter)
            )
            or 0,
            embedded_searchable_chunks=await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(LegalDocument, LegalDocument.doc_id == DocumentChunk.doc_id)
                .where(*searchable_filter, DocumentChunk.embedding_vector.is_not(None))
            )
            or 0,
            seed_documents=await session.scalar(
                select(func.count())
                .select_from(LegalDocument)
                .where(LegalDocument.doc_id.in_(SEED_DOC_IDS))
            )
            or 0,
        )


async def cutover(confirm: bool) -> int:
    readiness = await inspect_readiness()
    print(
        "READINESS: "
        f"real={readiness.real_documents}/{EXPECTED_REAL_DOCUMENTS}, "
        f"approved={readiness.approved_documents}/{EXPECTED_REAL_DOCUMENTS}, "
        f"embeddings={readiness.embedded_searchable_chunks}/{readiness.searchable_chunks}, "
        f"seeds={readiness.seed_documents}/{len(SEED_DOC_IDS)}"
    )
    if not confirm:
        print("DRY-RUN: no rows changed.")
        return 0 if readiness.ready else 2
    if not readiness.ready:
        print("BLOCKED: approval and embedding release gates have not passed.")
        return 2

    async with async_session_factory() as session:
        seeds = list(
            (
                await session.scalars(
                    select(LegalDocument).where(LegalDocument.doc_id.in_(SEED_DOC_IDS))
                )
            ).all()
        )
        for document in seeds:
            await session.delete(document)
        await session.commit()
    print(f"CUTOVER: removed {len(seeds)} allowlisted seed documents.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(cutover(args.confirm)))


if __name__ == "__main__":
    main()
