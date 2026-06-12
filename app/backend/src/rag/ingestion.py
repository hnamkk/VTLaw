"""Ingestion service: parse -> chunk -> embed -> persist (spec 10 §2, plan §2).

A single document goes through the full Phase 1+2 pipeline here. The function is
plain async and side-effect-scoped to one DB session, so it can be invoked from
a FastAPI ``BackgroundTasks`` today and swapped to Celery/RQ later without
touching the pipeline body.

Persistence denormalizes ``status``/``effective_date`` from the parent
``legal_documents`` row onto every chunk (spec 10 §3.2) so the mandatory active
filter (PRD F02) can run on ``document_chunks`` alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b, sha256
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.legal_document import LegalDocument
from src.rag.chunking import ChunkDraft, DocMeta, chunk_document
from src.rag.embedding import embed_texts
from src.rag.parsing import PARSER_WARNING_THRESHOLD, parse_document
from src.rag.qcvn_assets import extract_qcvn_assets

_ARTICLE_SCOPED_CHUNK_TYPES = {"dieu", "khoan", "diem"}


@dataclass
class IngestionReport:
    doc_id: str
    chunk_count: int
    parser_confidence: float
    warnings: list[str]
    asset_count: int = 0


def _validate_chunk_hierarchy(drafts: list[ChunkDraft]) -> None:
    invalid = [
        draft
        for draft in drafts
        if draft.chunk_type in _ARTICLE_SCOPED_CHUNK_TYPES and draft.article_num is None
    ]
    if not invalid:
        return
    sample = invalid[0]
    raise ValueError(
        "Chunk hierarchy invalid before embedding: "
        f"type={sample.chunk_type}, article_num=None, "
        f"source_order={sample.source_order}, text={sample.text_content[:120]!r}."
    )


async def ingest_document(
    session: AsyncSession,
    doc_id: str,
    file_path: str,
) -> IngestionReport:
    """Run the full ingestion pipeline for one already-registered document.

    The ``legal_documents`` row must already exist (created at upload time with
    its metadata); this fills in its chunks. Raises ValueError if the document
    is missing or parsing yields no publishable chunk (spec 10 §8).
    """
    document = await session.get(LegalDocument, doc_id)
    if document is None:
        raise ValueError(f"legal_documents row không tồn tại cho doc_id={doc_id!r}.")

    # Parse + embed BEFORE the advisory lock so we don't hold a DB transaction
    # open across slow IO (~seconds for 100+ chunks of OpenAI calls). The lock
    # only needs to cover the delete+insert window where two concurrent runs
    # would race; doing redundant parse/embed work in the loser is cheap
    # compared to blocking other DB connections.
    parsed = parse_document(file_path)
    meta = DocMeta(
        title=document.title,
        doc_type=document.doc_type,
        effective_date=document.effective_date.isoformat(),
        status=document.status,
        document_number=document.document_number,
        corpus=document.document_family or "road_law",
        parser_profile=document.parser_profile,
        parser_version=document.parser_version,
    )
    drafts = chunk_document(parsed, meta)
    if not drafts:
        raise ValueError(
            "Không tạo được chunk nào — văn bản rỗng hoặc parser thất bại. "
            "Không publish (spec 10 §8)."
        )

    # Fail before the embedding call so malformed parser output cannot spend
    # provider quota and then fail at the database constraint.
    _validate_chunk_hierarchy(drafts)

    vectors = await embed_texts([d.embedding_content for d in drafts])

    # Serialize concurrent persists for the same doc. pg_advisory_xact_lock takes
    # two signed int4 keys; we derive them deterministically (Python's built-in
    # hash() is randomized per-process so workers would never agree). Released
    # on commit/rollback automatically.
    digest = blake2b(doc_id.encode(), digest_size=8).digest()
    key1 = int.from_bytes(digest[:4], "big", signed=True)
    key2 = int.from_bytes(digest[4:], "big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:k1, :k2)"), {"k1": key1, "k2": key2})

    # Re-ingest is idempotent: drop existing chunks for this doc before insert.
    existing = await session.scalars(select(DocumentChunk).where(DocumentChunk.doc_id == doc_id))
    for row in existing:
        await session.delete(row)

    for draft, vector in zip(drafts, vectors, strict=True):
        session.add(
            DocumentChunk(
                doc_id=doc_id,
                text_content=draft.text_content,
                chunk_type=draft.chunk_type,
                chapter_num=draft.chapter_num,
                article_num=draft.article_num,
                clause_num=draft.clause_num,
                point_num=draft.point_num,
                canonical_provision_id=draft.canonical_provision_id,
                locator_type=draft.locator_type,
                locator_label=draft.locator_label,
                section_path=draft.section_path or draft.heading_path,
                section_number=draft.section_number,
                sign_codes=draft.sign_codes,
                figure_ids=draft.figure_ids,
                table_id=draft.table_id,
                corpus=document.document_family or "road_law",
                rag_enabled=document.rag_enabled,
                valid_from=document.valid_from or document.effective_date,
                valid_to=document.valid_to or document.expiry_date,
                provision_status=(
                    "future_effective"
                    if document.legal_status == "future_effective"
                    else "repealed"
                    if document.legal_status == "repealed"
                    else "active"
                ),
                content_hash=sha256(draft.text_content.encode("utf-8")).hexdigest(),
                embedding_model=settings.EMBEDDING_MODEL_NAME,
                embedding_version=document.index_version or "v1",
                parser_version=document.parser_version,
                status=document.status,
                effective_date=document.effective_date,
                metadata_json=draft.metadata_json(parsed.confidence),
                embedding_vector=vector,
            )
        )
    asset_count = 0
    if document.parser_profile == "qcvn":
        existing_assets = await session.scalars(
            select(DocumentAsset).where(
                DocumentAsset.doc_id == doc_id,
                DocumentAsset.asset_kind.in_(("sign_image", "sign_group")),
                DocumentAsset.publish_status == "pending",
            )
        )
        for asset in existing_assets:
            await session.delete(asset)

        asset_root = Path(__file__).resolve().parents[2] / "storage" / "assets"
        seen_checksums: set[str] = set()
        for asset in extract_qcvn_assets(
            Path(file_path),
            asset_root,
            document.source_checksum or document.doc_id,
        ):
            if asset.checksum in seen_checksums:
                continue
            seen_checksums.add(asset.checksum)
            session.add(
                DocumentAsset(
                    doc_id=doc_id,
                    asset_kind=asset.asset_kind,
                    checksum=asset.checksum,
                    mime_type=asset.mime_type,
                    source_locator=asset.source_locator,
                    relationship_id=asset.relationship_id,
                    original_format=Path(asset.storage_key).suffix.lstrip("."),
                    original_asset_key=asset.storage_key,
                    publish_status="pending",
                    caption=asset.source_locator,
                    mapping_confidence=asset.mapping_confidence,
                )
            )
            asset_count += 1
    await session.commit()

    warnings = list(parsed.warnings)
    if parsed.confidence < PARSER_WARNING_THRESHOLD:
        warnings.append("parser_confidence dưới ngưỡng — cần ADMIN duyệt trong HITL.")

    return IngestionReport(
        doc_id=doc_id,
        chunk_count=len(drafts),
        parser_confidence=parsed.confidence,
        warnings=warnings,
        asset_count=asset_count,
    )


__all__ = ["ingest_document", "IngestionReport"]
