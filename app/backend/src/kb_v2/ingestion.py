"""KB v2 ingestion workflow for the first DOCX vertical slice."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.kb_v2.metadata import normalize_document_role, normalize_document_type
from src.kb_v2.parser import build_canonical_nodes, parse_docx_into_artifacts
from src.kb_v2.proposals import build_summary_proposal, seed_initial_metadata_proposals
from src.kb_v2.retrieval_units import RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION
from src.models.kb_v2 import (
    KbV2DocumentRevision,
    KbV2LegalDocument,
    KbV2ReviewEvent,
    KbV2SourceAsset,
)
from src.storage.object_storage import build_kb_v2_object_key, get_object_storage

_UPLOAD_CHUNK_SIZE = 1024 * 1024
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class SavedKbV2Upload:
    local_path: Path
    storage_uri: str
    checksum_sha256: str
    original_filename: str
    file_size_bytes: int
    mime_type: str


@dataclass(frozen=True)
class KbV2IngestionResult:
    document: KbV2LegalDocument
    revision: KbV2DocumentRevision
    source_asset: KbV2SourceAsset
    canonical_nodes: list
    parser_warnings: list[str]
    parser_confidence: float


async def ingest_kb_v2_docx(
    session: AsyncSession,
    *,
    file: UploadFile,
    title: str,
    source_url: str,
    source_downloaded_at: date,
    source_note: str,
    document_number: str | None = None,
    document_type: str | None = None,
    document_role: str | None = None,
    issuing_authority: str | None = None,
    issued_date: date | None = None,
    effective_date: date | None = None,
    expiry_date: date | None = None,
    uploaded_by: str | None = None,
    existing_document: KbV2LegalDocument | None = None,
) -> KbV2IngestionResult:
    metadata_json = {"source_note": source_note.strip(), "source_url": source_url.strip()}
    if document_role:
        normalized_role = normalize_document_role(document_role)
        if normalized_role:
            metadata_json["document_role"] = normalized_role
    normalized_document_type = normalize_document_type(document_type)

    if existing_document is None:
        document = KbV2LegalDocument(
            document_id=str(uuid4()),
            title=title.strip(),
            document_number=document_number,
            document_type=normalized_document_type,
            issuing_authority=issuing_authority,
            issued_date=issued_date,
            effective_date=effective_date,
            expiry_date=expiry_date,
            legal_status="unknown",
            metadata_json=metadata_json,
        )
        proposal_document = document
        revision_number = 1
        upload_mode = "new_document"
    else:
        document = existing_document
        proposal_document = KbV2LegalDocument(
            document_id=document.document_id,
            title=title.strip(),
            document_number=document_number or document.document_number,
            document_type=normalized_document_type or document.document_type,
            issuing_authority=issuing_authority or document.issuing_authority,
            issued_date=issued_date or document.issued_date,
            effective_date=effective_date or document.effective_date,
            expiry_date=expiry_date or document.expiry_date,
            legal_status=document.legal_status,
            metadata_json={**(document.metadata_json or {}), **metadata_json},
        )
        revision_number = max((item.revision_number for item in document.revisions), default=0) + 1
        upload_mode = "replacement"

    revision = KbV2DocumentRevision(
        revision_id=str(uuid4()),
        document_id=document.document_id,
        revision_number=revision_number,
        ingestion_status="uploaded",
        review_status="needs_review",
        publication_status="draft",
        parser_version="kb-v2-p1",
        source_url=source_url.strip(),
        source_downloaded_at=source_downloaded_at,
        source_note=source_note.strip(),
        uploaded_by=uploaded_by,
        uploaded_at=datetime.now(tz=UTC),
    )

    saved_upload = await _save_source_docx(file, document_id=document.document_id, revision_id=revision.revision_id)

    duplicate = await session.scalar(
        select(KbV2SourceAsset).where(
            KbV2SourceAsset.asset_role == "source",
            KbV2SourceAsset.sha256 == saved_upload.checksum_sha256,
        )
    )
    if duplicate is not None:
        saved_upload.local_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "KB_DUPLICATE_SOURCE",
                "message": "Tệp DOCX này đã được upload trước đó trong KB v2. Hãy mở revision đang có để tiếp tục review.",
                "source_asset_id": duplicate.asset_id,
                "document_id": duplicate.document_id,
                "revision_id": duplicate.revision_id,
                "sha256": saved_upload.checksum_sha256,
            },
        )

    source_asset = KbV2SourceAsset(
        asset_id=str(uuid4()),
        document_id=document.document_id,
        revision_id=revision.revision_id,
        asset_role="source",
        storage_uri=saved_upload.storage_uri,
        original_filename=saved_upload.original_filename,
        mime_type=saved_upload.mime_type,
        sha256=saved_upload.checksum_sha256,
        file_size_bytes=saved_upload.file_size_bytes,
        source_url=source_url.strip(),
        source_downloaded_at=source_downloaded_at,
        source_note=source_note.strip(),
        metadata_json={"storage_backend": "object" if settings.OBJECT_STORAGE_ENABLED else "local"},
    )
    revision.checksum_sha256 = saved_upload.checksum_sha256

    # Persist the circular revision/source-asset references in two phases so
    # PostgreSQL never sees a foreign key before the referenced row exists.
    if existing_document is None:
        session.add(document)
    session.add(revision)
    await session.flush()
    session.add(source_asset)
    await session.flush()
    revision.source_asset_id = source_asset.asset_id

    artifacts = parse_docx_into_artifacts(
        source_path=str(saved_upload.local_path),
        title=proposal_document.title or saved_upload.original_filename,
    )
    revision.ingestion_status = "parsed" if artifacts.drafts else "parse_failed"
    canonical_nodes = build_canonical_nodes(
        revision_id=revision.revision_id,
        drafts=artifacts.drafts,
        parser_confidence=artifacts.parsed.confidence,
    )
    for node in canonical_nodes:
        structured_content = node.structured_content or {}
        if bool(structured_content.get("review_only")):
            node.review_status = "approved"
            continue
        if node.node_type in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION and "answerable" in structured_content:
            node.review_status = "approved"
            continue
        if node.node_type not in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION:
            node.review_status = "approved"
    metadata_proposals = seed_initial_metadata_proposals(document=proposal_document, revision=revision)
    summary_proposal = build_summary_proposal(
        document=proposal_document,
        revision=revision,
        canonical_nodes=canonical_nodes,
    )

    for proposal in metadata_proposals:
        session.add(proposal)
    for node in canonical_nodes:
        session.add(node)
    if summary_proposal is not None:
        session.add(summary_proposal)
    session.add(
        KbV2ReviewEvent(
            review_event_id=str(uuid4()),
            document_id=document.document_id,
            revision_id=revision.revision_id,
            entity_type="revision",
            entity_id=revision.revision_id,
            decision="created",
            actor_user_id=uploaded_by,
            details={
                "upload_mode": upload_mode,
                "previous_revision_id": _current_published_revision_id(document) if existing_document is not None else None,
                "ingestion_status": revision.ingestion_status,
                "canonical_node_count": len(canonical_nodes),
                "metadata_proposal_count": len(metadata_proposals),
                "parser_warnings": artifacts.parsed.warnings,
            },
        )
    )
    await session.commit()

    return KbV2IngestionResult(
        document=document,
        revision=revision,
        source_asset=source_asset,
        canonical_nodes=canonical_nodes,
        parser_warnings=list(artifacts.parsed.warnings),
        parser_confidence=artifacts.parsed.confidence,
    )


def _current_published_revision_id(document: KbV2LegalDocument) -> str | None:
    published = [
        revision
        for revision in document.revisions
        if revision.publication_status in {"published", "suspended"}
    ]
    if not published:
        return None
    return max(published, key=lambda item: item.revision_number).revision_id


async def _save_source_docx(
    file: UploadFile,
    *,
    document_id: str,
    revision_id: str,
) -> SavedKbV2Upload:
    safe_name = Path(file.filename or "source.docx").name
    if Path(safe_name).suffix.lower() != ".docx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNSUPPORTED_FILE_TYPE", "message": "KB v2 hiện chỉ nhận file DOCX."},
        )

    max_size_bytes = settings.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
    local_root = _kb_v2_local_root()
    tmp_dir = local_root / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid4().hex}-{safe_name}"

    digest = sha256()
    total_size = 0
    try:
        with tmp_path.open("xb") as target:
            while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail={
                            "code": "FILE_TOO_LARGE",
                            "message": f"File vượt quá giới hạn {settings.MAX_UPLOAD_FILE_SIZE_MB} MB.",
                        },
                    )
                digest.update(chunk)
                target.write(chunk)
        if total_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "EMPTY_FILE", "message": "File tải lên không có nội dung."},
            )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    checksum = digest.hexdigest()
    final_key = build_kb_v2_object_key(
        kind="source",
        document_id=document_id,
        revision_id=revision_id,
        sha256=checksum,
        extension="docx",
    )
    final_local_path = local_root / Path(final_key)
    final_local_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.replace(final_local_path)

    mime_type = mimetypes.guess_type(safe_name)[0] or _DOCX_MIME
    storage_uri = str(final_local_path.resolve())
    if settings.OBJECT_STORAGE_ENABLED:
        metadata = {"sha256": checksum, "document_id": document_id, "revision_id": revision_id}
        storage_uri = get_object_storage().upload_file(
            final_local_path,
            final_key,
            content_type=mime_type,
            metadata=metadata,
        )

    return SavedKbV2Upload(
        local_path=final_local_path,
        storage_uri=storage_uri,
        checksum_sha256=checksum,
        original_filename=safe_name,
        file_size_bytes=total_size,
        mime_type=mime_type,
    )


def _kb_v2_local_root() -> Path:
    configured = Path(settings.kb_local_storage_path)
    if configured.is_absolute():
        return configured
    return (Path(__file__).resolve().parents[4] / configured).resolve()
