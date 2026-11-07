"""Legacy admin queue module kept only for old-data maintenance and tests.

This router is intentionally not mounted in the current application runtime.
New admin workflows must use ``admin_legal_kb`` and the published-document
workspace.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas import (
    AdminDocumentChunkOut,
    AdminDocumentDetail,
    AdminDocumentHistoryItem,
    AdminDocumentItem,
    AdminDocumentsResponse,
    AdminDocumentSummary,
    DocumentRepealRequest,
    KbQueueApproveRequest,
    KbQueueDetailOut,
    KbQueueDocumentOut,
    KbQueueDraftRequest,
    KbQueueItemOut,
    KbQueueListResponse,
    KbQueueRejectRequest,
    KbQueueSummary,
)
from src.auth.dependencies import require_admin
from src.core.config import settings
from src.db.legacy_kb_support import reconcile_legacy_document_metadata
from src.db.session import async_session_factory, get_session
from src.kb.lifecycle import apply_current_state, current_legal_date, document_expiry_on
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.document_lifecycle_event import DocumentLifecycleEvent
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument
from src.models.user import User
from src.notifications.service import create_approval_notification, publish_notification
from src.rag.chunking import DocMeta, chunk_document
from src.rag.embedding import embed_texts
from src.rag.metadata_extraction import (
    build_canonical_title,
    extract_document_number_candidate,
    infer_document_number_from_filename,
)
from src.rag.parsing import PARSER_WARNING_THRESHOLD, parse_document
from src.rag.parsing.base import clean_extracted_text
from src.rag.qcvn_assets import extract_qcvn_assets
from src.storage.object_storage import get_object_storage, is_object_uri

router = APIRouter(prefix="/admin", tags=["admin-kb"], dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "storage" / "uploads"
_ASSET_DIR = Path(__file__).resolve().parents[3] / "storage" / "assets"
_RAW_DIR = Path(__file__).resolve().parents[3] / "storage" / "raw"
_ALLOWED_UPLOAD_SUFFIXES = {".docx", ".pdf"}
_ALLOWED_DOC_TYPES = {
    "LUAT",
    "BO_LUAT",
    "NGHI_DINH",
    "THONG_TU",
    "QUYET_DINH",
    "CONG_VAN",
    "QUY_CHUAN",
}
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_UPLOAD_SEMAPHORE = asyncio.Semaphore(max(1, settings.MAX_CONCURRENT_UPLOADS))
_REJECT_REASONS = {"parser_error", "duplicate", "metadata_invalid", "wrong_relation", "other"}
_REJECT_REASON_LABELS = {
    "metadata_invalid": "Thông tin không hợp lệ",
    "parser_error": "Lỗi phân tích hoặc trích xuất",
    "duplicate": "Trùng lặp văn bản",
    "wrong_relation": "Sai quan hệ thay thế",
    "other": "Lý do khác",
}
_REQUIRED_REVIEW_CHECKS = {
    "official_source_verified",
    "legal_status_verified",
    "source_order_verified",
    "corpus_scope_verified",
}
_DUPLICATE_WARNING_PREFIX = "Phat hien tai lieu co dau hieu trung lap"
_SCHEMA_OUTDATED_DETAIL = {
    "code": "DATABASE_SCHEMA_OUTDATED",
    "detail": "Co so du lieu chua duoc cap nhat.",
}


@dataclass(frozen=True)
class SavedUpload:
    safe_name: str
    local_path: str
    storage_path: str
    checksum: str


def _raise_schema_outdated(exc: Exception) -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_SCHEMA_OUTDATED_DETAIL
    ) from exc


def _is_schema_outdated_error(exc: Exception) -> bool:
    if isinstance(exc, (ProgrammingError, DBAPIError)):
        original = getattr(exc, "orig", None)
        if original is not None:
            name = original.__class__.__name__
            message = str(original).lower()
            if name == "UndefinedTable" or "relation" in message and "does not exist" in message:
                return True
    return "kb_update_queue" in str(exc).lower() and "does not exist" in str(exc).lower()


def _chunk_to_schema(chunk: DocumentChunk) -> AdminDocumentChunkOut:
    meta = chunk.metadata_json or {}
    return AdminDocumentChunkOut(
        chunk_id=chunk.chunk_id,
        chunk_type=chunk.chunk_type,
        article_num=chunk.article_num,
        clause_num=chunk.clause_num,
        point_num=chunk.point_num,
        source_order=meta.get("source_order"),
        content_kind=meta.get("content_kind", "legal_text"),
        text_content=chunk.text_content,
        display_path=meta.get("display_path"),
        parser_confidence=meta.get("parser_confidence"),
        source_page=meta.get("source_page"),
        has_embedding=chunk.embedding_vector is not None,
    )


def _document_to_queue_doc(document: LegalDocument | None) -> KbQueueDocumentOut | None:
    if document is None:
        return None
    return KbQueueDocumentOut(
        doc_id=document.doc_id,
        title=document.title,
        doc_type=document.doc_type,
        status=document.status,
        issuer=document.issuer,
        effective_date=document.effective_date,
        expiry_date=document.expiry_date,
        source_url=document.source_url,
        domain_tags=list(document.domain_tags or []),
    )


def _collect_document_warnings(document: LegalDocument, chunks: list[DocumentChunk]) -> list[str]:
    warnings: list[str] = []
    if not chunks:
        return warnings
    parser_scores = [
        c.metadata_json.get("parser_confidence")
        for c in chunks
        if isinstance(c.metadata_json, dict)
        and c.metadata_json.get("parser_confidence") is not None
    ]
    if parser_scores and min(parser_scores) < PARSER_WARNING_THRESHOLD:
        warnings.append("Parser confidence dưới ngưỡng, cần duyệt kỹ.")
    if not any(chunk.article_num is not None for chunk in chunks):
        warnings.append("Chunk chưa gắn được Điều/Khoản rõ ràng.")
    return warnings


def _is_hidden_queue_warning(value: str) -> bool:
    return (
        value.strip().lower()
        == "chưa có url nguồn chính thức; không được approve trước khi bổ sung."
    )


def _visible_queue_warnings(warnings: list[str] | None) -> list[str]:
    return [warning for warning in (warnings or []) if not _is_hidden_queue_warning(warning)]


def _queue_has_duplicate_candidates(queue: KbUpdateQueue) -> bool:
    candidates = (queue.extracted_metadata or {}).get("duplicate_candidates")
    return isinstance(candidates, list) and len(candidates) > 0


def _reviewer_note_required_for_approval(queue: KbUpdateQueue) -> bool:
    return bool(_visible_queue_warnings(queue.warning_messages)) or _queue_has_duplicate_candidates(
        queue
    )


def _structure_summary(chunks: list[DocumentChunk]) -> dict[str, int]:
    return {
        "chunks": len(chunks),
        "articles": len({chunk.article_num for chunk in chunks if chunk.article_num is not None}),
        "clauses": len(
            {
                (chunk.article_num, chunk.clause_num)
                for chunk in chunks
                if chunk.article_num is not None and chunk.clause_num is not None
            }
        ),
        "points": len({chunk.point_num for chunk in chunks if chunk.point_num}),
    }


def _sort_chunks_in_source_order(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
    indexed = list(enumerate(chunks))
    return [
        chunk
        for _, chunk in sorted(
            indexed,
            key=lambda pair: (
                not isinstance((pair[1].metadata_json or {}).get("source_order"), int),
                (pair[1].metadata_json or {}).get("source_order", pair[0]),
            ),
        )
    ]


def _queue_source_path(source_path: str | None) -> Path | None:
    if not source_path:
        return None
    if is_object_uri(source_path):
        return None
    try:
        path = Path(source_path).resolve()
    except (OSError, RuntimeError):
        return None
    if not path.is_file() or not any(
        path.is_relative_to(root.resolve()) for root in (_UPLOAD_DIR, _RAW_DIR)
    ):
        return None
    return path


def _remove_uploaded_source(source_path: str | None) -> None:
    if not source_path:
        return
    if is_object_uri(source_path):
        try:
            get_object_storage().delete_object(source_path)
        except Exception:
            return
        return
    try:
        path = Path(source_path).resolve()
        upload_root = _UPLOAD_DIR.resolve()
        if path.is_file() and path.is_relative_to(upload_root):
            path.unlink(missing_ok=True)
    except OSError:
        return


def _is_source_checksum_integrity_error(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return "uq_legal_docs_source_checksum" in message or (
        "source_checksum" in message and "unique" in message
    )


def _queue_item_to_schema(queue: KbUpdateQueue, document: LegalDocument) -> KbQueueItemOut:
    visible_warnings = _visible_queue_warnings(queue.warning_messages)
    return KbQueueItemOut(
        queue_id=queue.queue_id,
        doc_id=document.doc_id,
        target_doc_id=queue.target_doc_id,
        title=document.title,
        issuer=document.issuer,
        doc_type=document.doc_type,
        effective_date=document.effective_date,
        review_status=queue.review_status,
        processing_status=queue.processing_status,
        change_type=queue.change_type,
        parser_confidence=queue.parser_confidence,
        warning_count=len(visible_warnings),
        source_file_name=queue.source_file_name,
        created_at=queue.created_at,
        reviewed_at=queue.reviewed_at,
    )


def _related_queue_clause(document_id: str):
    return or_(
        KbUpdateQueue.doc_id == document_id,
        KbUpdateQueue.target_doc_id == document_id,
    )


def _is_metadata_only_update(queue: KbUpdateQueue) -> bool:
    return bool((queue.extracted_metadata or {}).get("metadata_only"))


def _metadata_matches_document(left: LegalDocument, right: LegalDocument) -> bool:
    return (
        left.title == right.title
        and left.doc_type == right.doc_type
        and left.issuer == right.issuer
        and left.source_url == right.source_url
        and left.effective_date == right.effective_date
        and left.expiry_date == right.expiry_date
        and list(left.domain_tags or []) == list(right.domain_tags or [])
    )


def _normalize_duplicate_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(clean_extracted_text(value).lower().split())


def _duplicate_document_payload(document: LegalDocument, reason: str | None = None) -> dict:
    payload = {
        "doc_id": document.doc_id,
        "title": document.title,
        "doc_type": document.doc_type,
        "status": document.status,
        "review_status": document.review_status,
        "effective_date": document.effective_date.isoformat(),
        "issuer": document.issuer,
        "source_url": document.source_url,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _duplicate_source_detail(
    source_checksum: str,
    duplicate: LegalDocument | None,
) -> dict:
    detail = {
        "code": "DUPLICATE_SOURCE",
        "message": "Tep nguon trung checksum voi mot van ban khac.",
        "source_checksum": source_checksum,
        "duplicate_document": _duplicate_document_payload(duplicate)
        if duplicate is not None
        else None,
    }
    return detail


def _apply_duplicate_candidates(
    warnings: list[str],
    extracted_metadata: dict,
    candidates: list[dict],
) -> tuple[list[str], dict]:
    next_warnings = [
        warning for warning in warnings if not warning.startswith(_DUPLICATE_WARNING_PREFIX)
    ]
    next_metadata = dict(extracted_metadata)
    if candidates:
        next_warnings.append(
            f"{_DUPLICATE_WARNING_PREFIX}: {len(candidates)} tai lieu can reviewer doi chieu."
        )
        next_metadata["duplicate_candidates"] = candidates
    else:
        next_metadata.pop("duplicate_candidates", None)
    return next_warnings, next_metadata


async def _find_exact_duplicate_by_checksum(
    session: AsyncSession,
    source_checksum: str,
    *,
    exclude_doc_id: str | None = None,
) -> LegalDocument | None:
    stmt = (
        select(LegalDocument)
        .where(LegalDocument.source_checksum == source_checksum)
        .order_by(LegalDocument.created_at.desc())
        .limit(1)
    )
    if exclude_doc_id:
        stmt = stmt.where(LegalDocument.doc_id != exclude_doc_id)
    return await session.scalar(stmt)


async def _resolve_upload_target_document(
    session: AsyncSession,
    *,
    change_type: str,
    target_doc_id: str | None,
    exclude_queue_id: str | None = None,
) -> LegalDocument | None:
    if change_type == "create":
        if target_doc_id:
            raise HTTPException(
                status_code=422,
                detail="target_doc_id is only allowed for update requests",
            )
        return None

    if change_type not in {"update", "repeal"}:
        raise HTTPException(status_code=422, detail="Unsupported change_type")

    if not target_doc_id:
        raise HTTPException(status_code=422, detail=f"target_doc_id is required for {change_type}")

    target_document = await session.get(LegalDocument, target_doc_id)
    if target_document is None:
        raise HTTPException(status_code=404, detail="Target document not found")
    allowed_statuses = {"active", "repealed"} if change_type == "update" else {"active"}
    if (
        target_document.review_status != "approved"
        or target_document.status not in allowed_statuses
    ):
        raise HTTPException(
            status_code=409,
            detail="Target document is not eligible for update",
        )

    pending_stmt = (
        select(KbUpdateQueue.queue_id)
        .where(
            KbUpdateQueue.target_doc_id == target_doc_id,
            KbUpdateQueue.change_type.in_(("update", "repeal")),
            KbUpdateQueue.review_status == "pending",
        )
        .limit(1)
    )
    if exclude_queue_id:
        pending_stmt = pending_stmt.where(KbUpdateQueue.queue_id != exclude_queue_id)
    pending_update = await session.scalar(pending_stmt)
    if pending_update is not None:
        raise HTTPException(
            status_code=409,
            detail="Target document already has a pending lifecycle change",
        )

    return target_document


async def _find_duplicate_candidates(
    session: AsyncSession,
    *,
    title: str,
    doc_type: str,
    issuer: str,
    effective_date: date,
    source_url: str | None,
    exclude_doc_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    normalized_title = _normalize_duplicate_text(title)
    normalized_issuer = _normalize_duplicate_text(issuer)
    normalized_source_url = source_url.strip() if source_url else None
    stmt = (
        select(LegalDocument)
        .where(
            LegalDocument.doc_type == doc_type.strip(),
            LegalDocument.effective_date == effective_date,
        )
        .order_by(LegalDocument.created_at.desc())
        .limit(20)
    )
    if exclude_doc_id:
        stmt = stmt.where(LegalDocument.doc_id != exclude_doc_id)
    documents = list((await session.scalars(stmt)).all())
    candidates: list[dict] = []
    for document in documents:
        reasons: list[str] = []
        if (
            normalized_source_url
            and document.source_url
            and document.source_url.strip() == normalized_source_url
        ):
            reasons.append("source_url")
        if (
            normalized_title
            and normalized_issuer
            and _normalize_duplicate_text(document.title) == normalized_title
            and _normalize_duplicate_text(document.issuer) == normalized_issuer
        ):
            reasons.append("title_issuer_effective_date")
        if not reasons:
            continue
        candidates.append(_duplicate_document_payload(document, ",".join(reasons)))
        if len(candidates) >= limit:
            break
    return candidates


async def _save_upload(file: UploadFile) -> SavedUpload:
    async with _UPLOAD_SEMAPHORE:
        safe_name = Path(file.filename or "document").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in _ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "UNSUPPORTED_FILE_TYPE",
                    "message": "Chỉ hỗ trợ file PDF hoặc DOCX.",
                },
            )

        max_size_bytes = settings.MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        stored_name = f"{timestamp}-{uuid4().hex}-{safe_name}"
        stored_path = _UPLOAD_DIR / stored_name
        digest = sha256()
        total_size = 0
        try:
            with stored_path.open("xb") as target:
                while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
                    total_size += len(chunk)
                    if total_size > max_size_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail={
                                "code": "FILE_TOO_LARGE",
                                "message": (
                                    f"File vượt quá giới hạn {settings.MAX_UPLOAD_FILE_SIZE_MB} MB."
                                ),
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
            stored_path.unlink(missing_ok=True)
            raise
        checksum = digest.hexdigest()
        storage_path = str(stored_path)
        if settings.OBJECT_STORAGE_ENABLED:
            object_key = f"uploads/{checksum[:2]}/{checksum}-{safe_name}"
            media_type, _ = mimetypes.guess_type(safe_name)
            storage_path = get_object_storage().upload_file(
                stored_path,
                object_key,
                content_type=media_type,
            )
        return SavedUpload(
            safe_name=safe_name,
            local_path=str(stored_path),
            storage_path=storage_path,
            checksum=checksum,
        )


async def _prepare_pending_chunks(
    session: AsyncSession,
    document: LegalDocument,
    source_path: str,
) -> tuple[int, float | None, list[str], dict, str | None]:
    try:
        parsed = parse_document(source_path)
        drafts = chunk_document(
            parsed,
            DocMeta(
                title=document.title,
                doc_type=document.doc_type,
                effective_date=document.effective_date.isoformat(),
                status=document.status,
                document_number=document.document_number,
                corpus=document.document_family or "road_law",
                parser_profile=document.parser_profile,
                parser_version=document.parser_version,
            ),
        )
        preview_lines: list[str] = []
        for block in parsed.blocks:
            if block.text.strip():
                preview_lines.append(block.text.strip())
            if len(" ".join(preview_lines)) > 1600:
                break
        vectors = await embed_texts([draft.embedding_content for draft in drafts])
        for draft, vector in zip(drafts, vectors, strict=True):
            session.add(
                DocumentChunk(
                    doc_id=document.doc_id,
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
                    provision_status="future_effective"
                    if document.legal_status == "future_effective"
                    else "active",
                    content_hash=sha256(draft.text_content.encode("utf-8")).hexdigest(),
                    embedding_model="text-embedding-3-small",
                    embedding_version=document.index_version or "v1",
                    parser_version=document.parser_version,
                    status="pending_review",
                    effective_date=document.effective_date,
                    metadata_json=draft.metadata_json(parsed.confidence),
                    embedding_vector=vector,
                )
            )
        asset_count = 0
        if document.parser_profile == "qcvn":
            seen_checksums: set[str] = set()
            for asset in extract_qcvn_assets(
                Path(source_path),
                _ASSET_DIR,
                document.source_checksum or document.doc_id,
            ):
                if asset.checksum in seen_checksums:
                    continue
                seen_checksums.add(asset.checksum)
                session.add(
                    DocumentAsset(
                        doc_id=document.doc_id,
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
        warnings = list(parsed.warnings)
        if parsed.confidence < PARSER_WARNING_THRESHOLD:
            warnings.append("Parser confidence dưới ngưỡng.")
        document_number_candidate = extract_document_number_candidate("\n".join(preview_lines))
        metadata = {
            "preview_text": "\n\n".join(preview_lines)[:4000],
            "chunk_count": len(drafts),
            "asset_count": asset_count,
            "document_number_candidate": document_number_candidate,
            "canonical_title_candidate": build_canonical_title(
                document.doc_type,
                document_number_candidate,
                document.title,
            ),
        }
        return len(drafts), parsed.confidence, warnings, metadata, None
    except Exception as exc:  # pragma: no cover - defensive error capture for upload flow
        return 0, None, [str(exc)], {"preview_text": ""}, str(exc)


@router.get("/documents", response_model=AdminDocumentsResponse)
async def list_admin_documents(
    q: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    doc_type: str | None = Query(None),
    issuer: str | None = Query(None),
    year: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_session),
):
    try:
        filtered_documents = select(LegalDocument.doc_id)
        if q:
            search = f"%{q.strip()}%"
            filtered_documents = filtered_documents.where(
                or_(LegalDocument.title.ilike(search), LegalDocument.issuer.ilike(search))
            )
        if status_filter:
            normalized_status = status_filter.strip()
            if normalized_status == "future_effective":
                filtered_documents = filtered_documents.where(
                    LegalDocument.review_status == "approved",
                    LegalDocument.legal_status == "future_effective",
                )
            elif normalized_status == "pending_review":
                filtered_documents = filtered_documents.where(
                    LegalDocument.status == "pending_review",
                    LegalDocument.review_status == "pending",
                )
            else:
                filtered_documents = filtered_documents.where(
                    LegalDocument.status == normalized_status
                )
        if doc_type:
            filtered_documents = filtered_documents.where(
                LegalDocument.doc_type == doc_type.strip()
            )
        if issuer:
            filtered_documents = filtered_documents.where(
                LegalDocument.issuer.ilike(f"%{issuer.strip()}%")
            )
        if year:
            filtered_documents = filtered_documents.where(
                func.extract("year", LegalDocument.effective_date) == year
            )

        filtered_documents = filtered_documents.subquery()

        chunk_agg = (
            select(
                DocumentChunk.doc_id.label("doc_id"),
                func.count(DocumentChunk.chunk_id).label("chunk_count"),
                func.count(DocumentChunk.embedding_vector).label("indexed_chunk_count"),
            )
            .group_by(DocumentChunk.doc_id)
            .subquery()
        )
        pending_queue_count = (
            select(func.count())
            .where(
                _related_queue_clause(LegalDocument.doc_id),
                KbUpdateQueue.review_status == "pending",
            )
            .correlate(LegalDocument)
            .scalar_subquery()
        )
        latest_source_file_name = (
            select(KbUpdateQueue.source_file_name)
            .where(
                _related_queue_clause(LegalDocument.doc_id),
                KbUpdateQueue.review_status == "approved",
                KbUpdateQueue.source_path.is_not(None),
            )
            .order_by(KbUpdateQueue.reviewed_at.desc().nullslast(), KbUpdateQueue.created_at.desc())
            .correlate(LegalDocument)
            .limit(1)
            .scalar_subquery()
        )
        latest_source_queue_id = (
            select(KbUpdateQueue.queue_id)
            .where(
                _related_queue_clause(LegalDocument.doc_id),
                KbUpdateQueue.review_status == "approved",
                KbUpdateQueue.source_path.is_not(None),
            )
            .order_by(KbUpdateQueue.reviewed_at.desc().nullslast(), KbUpdateQueue.created_at.desc())
            .correlate(LegalDocument)
            .limit(1)
            .scalar_subquery()
        )

        base_query = (
            select(
                LegalDocument,
                func.coalesce(chunk_agg.c.chunk_count, 0).label("chunk_count"),
                func.coalesce(chunk_agg.c.indexed_chunk_count, 0).label("indexed_chunk_count"),
                func.coalesce(pending_queue_count, 0).label("pending_queue_count"),
                latest_source_file_name.label("source_file_name"),
                latest_source_queue_id.label("source_queue_id"),
            )
            .join(filtered_documents, filtered_documents.c.doc_id == LegalDocument.doc_id)
            .outerjoin(chunk_agg, chunk_agg.c.doc_id == LegalDocument.doc_id)
            .order_by(LegalDocument.created_at.desc())
        )

        total = (
            await db_session.execute(select(func.count()).select_from(filtered_documents))
        ).scalar() or 0
        result = await db_session.execute(
            base_query.offset((page - 1) * page_size).limit(page_size)
        )
        items = [
            AdminDocumentItem(
                doc_id=document.doc_id,
                title=document.title,
                doc_type=document.doc_type,
                status=document.status,
                review_status=document.review_status,
                legal_status=document.legal_status,
                effective_date=document.effective_date,
                expiry_date=document.expiry_date,
                valid_from=document.valid_from,
                valid_to=document.valid_to,
                issuer=document.issuer,
                source_url=document.source_url,
                chunk_count=chunk_count or 0,
                indexed_chunk_count=indexed_chunk_count or 0,
                pending_queue_count=pending_count or 0,
                source_file_name=source_file_name,
                source_download_url=f"/api/v1/admin/queue/{source_queue_id}/source"
                if source_queue_id
                else None,
                created_at=document.created_at,
            )
            for document, chunk_count, indexed_chunk_count, pending_count, source_file_name, source_queue_id in result.all()
        ]

        total_docs = (
            await db_session.execute(select(func.count()).select_from(LegalDocument))
        ).scalar() or 0
        active = (
            await db_session.execute(
                select(func.count())
                .select_from(LegalDocument)
                .where(LegalDocument.status == "active")
            )
        ).scalar() or 0
        pending_review = (
            await db_session.execute(
                select(func.count())
                .select_from(LegalDocument)
                .where(
                    LegalDocument.status == "pending_review",
                    LegalDocument.review_status == "pending",
                )
            )
        ).scalar() or 0
        future_effective = (
            await db_session.execute(
                select(func.count())
                .select_from(LegalDocument)
                .where(
                    LegalDocument.review_status == "approved",
                    LegalDocument.legal_status == "future_effective",
                )
            )
        ).scalar() or 0
        repealed = (
            await db_session.execute(
                select(func.count())
                .select_from(LegalDocument)
                .where(LegalDocument.status == "repealed")
            )
        ).scalar() or 0
        failed = (
            await db_session.execute(
                select(func.count())
                .select_from(KbUpdateQueue)
                .where(KbUpdateQueue.processing_status == "failed")
            )
        ).scalar() or 0

        return AdminDocumentsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            summary=AdminDocumentSummary(
                total=total_docs,
                active=active,
                pending_review=pending_review,
                future_effective=future_effective,
                repealed=repealed,
                processing_failed=failed,
            ),
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.get("/documents/{doc_id}", response_model=AdminDocumentDetail)
async def get_admin_document_detail(
    doc_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    try:
        document = await db_session.scalar(
            select(LegalDocument)
            .where(LegalDocument.doc_id == doc_id)
            .options(selectinload(LegalDocument.chunks), selectinload(LegalDocument.queue_items))
        )
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        related_queue_items = list(
            (
                await db_session.scalars(
                    select(KbUpdateQueue)
                    .where(_related_queue_clause(document.doc_id))
                    .order_by(KbUpdateQueue.created_at.desc())
                )
            ).all()
        )
        latest_queue = next(
            (
                item
                for item in related_queue_items
                if item.review_status == "approved" and item.source_path
            ),
            None,
        )
        chunks = _sort_chunks_in_source_order(document.chunks)
        warnings = _collect_document_warnings(document, chunks)
        history = [
            AdminDocumentHistoryItem(
                queue_id=item.queue_id,
                change_type=item.change_type,
                review_status=item.review_status,
                processing_status=item.processing_status,
                source_file_name=item.source_file_name,
                reviewer_note=item.reviewer_note,
                reject_reason=item.reject_reason,
                reviewed_at=item.reviewed_at,
                created_at=item.created_at,
            )
            for item in related_queue_items
        ]
        return AdminDocumentDetail(
            doc_id=document.doc_id,
            title=document.title,
            doc_type=document.doc_type,
            status=document.status,
            review_status=document.review_status,
            legal_status=document.legal_status,
            effective_date=document.effective_date,
            expiry_date=document.expiry_date,
            valid_from=document.valid_from,
            valid_to=document.valid_to,
            issuer=document.issuer,
            source_url=document.source_url,
            chunk_count=len(chunks),
            indexed_chunk_count=sum(1 for chunk in chunks if chunk.embedding_vector is not None),
            pending_queue_count=sum(
                1 for item in related_queue_items if item.review_status == "pending"
            ),
            created_at=document.created_at,
            replaced_by_id=document.replaced_by_id,
            domain_tags=list(document.domain_tags or []),
            warnings=warnings,
            source_file_name=latest_queue.source_file_name if latest_queue else None,
            structure_summary=_structure_summary(chunks),
            history=history,
            chunks=[_chunk_to_schema(chunk) for chunk in chunks],
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.post(
    "/documents/{doc_id}/metadata-update",
    response_model=KbQueueDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_metadata_update_queue(
    doc_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    try:
        target_document = await _resolve_upload_target_document(
            db_session,
            change_type="update",
            target_doc_id=doc_id,
        )
        if target_document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        warnings: list[str] = []
        extracted_metadata = {
            "metadata_only": True,
            "target_doc_id": target_document.doc_id,
            "source_document_version": target_document.source_version,
        }
        document = LegalDocument(
            title=target_document.title,
            document_number=target_document.document_number,
            document_family=target_document.document_family,
            doc_type=target_document.doc_type,
            status="pending_review",
            review_status="pending",
            legal_status=target_document.legal_status,
            rag_scope=target_document.rag_scope,
            rag_enabled=target_document.rag_enabled,
            effective_date=target_document.effective_date,
            expiry_date=target_document.expiry_date,
            valid_from=target_document.valid_from or target_document.effective_date,
            valid_to=target_document.valid_to or target_document.expiry_date,
            parser_profile=target_document.parser_profile,
            parser_version=target_document.parser_version,
            index_version=target_document.index_version,
            issuer=target_document.issuer,
            source_url=target_document.source_url,
            domain_tags=list(target_document.domain_tags or []),
        )
        # Metadata-only staging must not copy source_checksum; the active target
        # keeps the unique checksum until approval copies metadata back.
        db_session.add(document)
        await db_session.flush()

        queue = KbUpdateQueue(
            doc_id=document.doc_id,
            target_doc_id=target_document.doc_id,
            change_type="update",
            review_status="pending",
            processing_status="ready",
            warning_messages=warnings,
            extracted_metadata=extracted_metadata,
        )
        db_session.add(queue)
        await db_session.commit()
        await db_session.refresh(queue)
        return await get_kb_queue_detail(queue.queue_id, db_session)
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.post(
    "/documents/{doc_id}/repeal",
    response_model=KbQueueDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_repeal_queue(
    doc_id: str,
    payload: DocumentRepealRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    """Create a reviewable expiry transition without changing the active document."""
    try:
        target_document = await _resolve_upload_target_document(
            db_session,
            change_type="repeal",
            target_doc_id=doc_id,
        )
        if target_document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if payload.expiry_date <= target_document.effective_date:
            raise HTTPException(
                status_code=422,
                detail="Ngày hết hiệu lực phải sau ngày có hiệu lực.",
            )

        replacement = None
        replacement_id = str(payload.replaced_by_id) if payload.replaced_by_id else None
        if replacement_id:
            if replacement_id == target_document.doc_id:
                raise HTTPException(
                    status_code=422, detail="Văn bản không thể tự thay thế chính nó."
                )
            replacement = await db_session.get(LegalDocument, replacement_id)
            if replacement is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy văn bản thay thế.")
            if replacement.review_status != "approved" or replacement.status == "repealed":
                raise HTTPException(
                    status_code=409,
                    detail="Văn bản thay thế chưa được duyệt hoặc đã hết hiệu lực.",
                )

        staging_document = LegalDocument(
            title=target_document.title,
            document_number=target_document.document_number,
            document_family=target_document.document_family,
            doc_type=target_document.doc_type,
            status="pending_review",
            review_status="pending",
            legal_status=target_document.legal_status,
            rag_scope=target_document.rag_scope,
            rag_enabled=target_document.rag_enabled,
            effective_date=target_document.effective_date,
            expiry_date=payload.expiry_date,
            valid_from=target_document.valid_from or target_document.effective_date,
            valid_to=payload.expiry_date,
            parser_profile=target_document.parser_profile,
            parser_version=target_document.parser_version,
            index_version=target_document.index_version,
            issuer=target_document.issuer,
            source_url=target_document.source_url,
            domain_tags=list(target_document.domain_tags or []),
        )
        db_session.add(staging_document)
        await db_session.flush()

        queue = KbUpdateQueue(
            doc_id=staging_document.doc_id,
            target_doc_id=target_document.doc_id,
            change_type="repeal",
            review_status="pending",
            processing_status="ready",
            warning_messages=[],
            extracted_metadata={
                "lifecycle_only": True,
                "target_doc_id": target_document.doc_id,
                "expiry_date": payload.expiry_date.isoformat(),
                "repeal_reason": payload.reason.strip(),
                "replaced_by_id": replacement.doc_id if replacement else None,
            },
            reviewer_draft_note=payload.reason.strip(),
            created_by=current_user.user_id,
        )
        db_session.add(queue)
        await db_session.commit()
        await db_session.refresh(queue)
        return await get_kb_queue_detail(queue.queue_id, db_session)
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.get("/queue", response_model=KbQueueListResponse)
async def list_kb_queue(
    tab: str = Query("pending"),
    q: str | None = Query(None),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db_session: AsyncSession = Depends(get_session),
):
    try:
        query = (
            select(KbUpdateQueue, LegalDocument)
            .join(LegalDocument, LegalDocument.doc_id == KbUpdateQueue.doc_id)
            .options(selectinload(KbUpdateQueue.document))
        )
        if tab in {"pending", "approved", "rejected"}:
            query = query.where(KbUpdateQueue.review_status == tab)
        if q:
            search = f"%{q.strip()}%"
            query = query.where(
                or_(LegalDocument.title.ilike(search), LegalDocument.issuer.ilike(search))
            )

        if sort == "oldest":
            query = query.order_by(KbUpdateQueue.created_at.asc())
        elif sort == "warnings":
            query = query.order_by(
                func.cardinality(KbUpdateQueue.warning_messages).desc(),
                KbUpdateQueue.created_at.desc(),
            )
        else:
            query = query.order_by(KbUpdateQueue.created_at.desc())

        total_query = select(func.count()).select_from(query.subquery())
        total = int((await db_session.execute(total_query)).scalar_one() or 0)
        rows = (
            await db_session.execute(query.offset((page - 1) * page_size).limit(page_size))
        ).all()
        counts = (
            await db_session.execute(
                select(
                    func.sum(case((KbUpdateQueue.review_status == "pending", 1), else_=0)),
                    func.sum(case((KbUpdateQueue.review_status == "approved", 1), else_=0)),
                    func.sum(case((KbUpdateQueue.review_status == "rejected", 1), else_=0)),
                )
            )
        ).one()

        return KbQueueListResponse(
            items=[_queue_item_to_schema(queue, document) for queue, document in rows],
            total=total,
            page=page,
            page_size=page_size,
            summary=KbQueueSummary(
                pending=counts[0] or 0,
                approved=counts[1] or 0,
                rejected=counts[2] or 0,
            ),
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.get("/queue/{queue_id}", response_model=KbQueueDetailOut)
async def get_kb_queue_detail(
    queue_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    try:
        queue = await db_session.scalar(
            select(KbUpdateQueue)
            .where(KbUpdateQueue.queue_id == queue_id)
            .options(
                selectinload(KbUpdateQueue.document).selectinload(LegalDocument.chunks),
                selectinload(KbUpdateQueue.document).selectinload(LegalDocument.assets),
                selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.chunks),
                selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.assets),
            )
        )
        if queue is None or queue.document is None:
            raise HTTPException(status_code=404, detail="Queue item not found")

        chunks = _sort_chunks_in_source_order(queue.document.chunks)
        return KbQueueDetailOut(
            queue_id=queue.queue_id,
            doc_id=queue.doc_id,
            target_doc_id=queue.target_doc_id,
            change_type=queue.change_type,
            review_status=queue.review_status,
            processing_status=queue.processing_status,
            parser_confidence=queue.parser_confidence,
            warning_messages=list(queue.warning_messages or []),
            extracted_metadata=dict(queue.extracted_metadata or {}),
            review_checklist=dict(queue.review_checklist or {}),
            reviewer_draft_note=queue.reviewer_draft_note,
            reviewer_note=queue.reviewer_note,
            reject_reason=queue.reject_reason,
            processing_error=queue.processing_error,
            source_file_name=queue.source_file_name,
            created_at=queue.created_at,
            reviewed_at=queue.reviewed_at,
            document=_document_to_queue_doc(queue.document),
            target_document=_document_to_queue_doc(queue.target_document),
            chunks=[_chunk_to_schema(chunk) for chunk in chunks],
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.get("/queue/{queue_id}/source")
async def read_kb_queue_source(
    queue_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    try:
        queue = await db_session.scalar(
            select(KbUpdateQueue)
            .where(KbUpdateQueue.queue_id == queue_id)
            .options(selectinload(KbUpdateQueue.document))
        )
        if queue is None or queue.source_path is None:
            raise HTTPException(status_code=404, detail="Queue item not found")

        media_type, _ = mimetypes.guess_type(queue.source_file_name or "")
        media_type = media_type or "application/octet-stream"
        disposition = "inline" if media_type == "application/pdf" else "attachment"
        if is_object_uri(queue.source_path):
            file_name = queue.source_file_name or "source"
            url = get_object_storage().public_or_presigned_url(
                queue.source_path,
                content_disposition=f'{disposition}; filename="{file_name}"',
            )
            return RedirectResponse(
                url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Cache-Control": "private, max-age=300"},
            )

        source_path = _queue_source_path(queue.source_path)
        if source_path is None:
            raise HTTPException(status_code=404, detail="Source file not available")

        return FileResponse(
            source_path,
            media_type=media_type,
            filename=queue.source_file_name or source_path.name,
            content_disposition_type=disposition,
            headers={"Cache-Control": "private, max-age=300"},
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.post("/queue/upload", response_model=KbQueueDetailOut, status_code=status.HTTP_201_CREATED)
async def upload_kb_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form(...),
    issuer: str = Form(...),
    effective_date: str = Form(...),
    source_url: str | None = Form(None),
    domain_tags: str | None = Form(None),
    change_type: str = Form("create"),
    target_doc_id: str | None = Form(None),
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    try:
        if change_type not in {"create", "update"}:
            raise HTTPException(status_code=422, detail="Unsupported change_type")
        normalized_doc_type = doc_type.strip()
        if normalized_doc_type not in _ALLOWED_DOC_TYPES:
            raise HTTPException(status_code=422, detail="Unsupported doc_type")

        try:
            effective = date.fromisoformat(effective_date)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Invalid effective_date") from exc

        parsed_tags = []
        if domain_tags:
            try:
                parsed_tags = json.loads(domain_tags)
                if not isinstance(parsed_tags, list):
                    raise ValueError
            except ValueError:
                parsed_tags = [item.strip() for item in domain_tags.split(",") if item.strip()]

        clean_title = clean_extracted_text(title)
        clean_issuer = clean_extracted_text(issuer)
        target_document = await _resolve_upload_target_document(
            db_session,
            change_type=change_type,
            target_doc_id=target_doc_id,
        )
        saved_upload = await _save_upload(file)
        safe_name = saved_upload.safe_name
        stored_path = saved_upload.local_path
        source_checksum = saved_upload.checksum
        document_number = infer_document_number_from_filename(safe_name)
        canonical_title = build_canonical_title(
            normalized_doc_type,
            document_number,
            clean_title,
        )
        duplicate = await _find_exact_duplicate_by_checksum(
            db_session,
            source_checksum,
            exclude_doc_id=target_document.doc_id if target_document else None,
        )
        if duplicate is not None:
            _remove_uploaded_source(saved_upload.storage_path)
            _remove_uploaded_source(stored_path)
            raise HTTPException(
                status_code=409,
                detail=_duplicate_source_detail(source_checksum, duplicate),
            )
        duplicate_candidates = await _find_duplicate_candidates(
            db_session,
            title=clean_title,
            doc_type=normalized_doc_type,
            issuer=clean_issuer,
            effective_date=effective,
            source_url=source_url,
            exclude_doc_id=target_document.doc_id if target_document else None,
        )
        document = LegalDocument(
            title=canonical_title,
            document_number=document_number,
            doc_type=normalized_doc_type,
            status="pending_review",
            review_status="pending",
            legal_status="future_effective" if effective > date.today() else "active",
            rag_scope="enabled",
            rag_enabled=True,
            effective_date=effective,
            valid_from=effective,
            source_checksum=source_checksum if target_document is None else None,
            parser_profile="qcvn" if normalized_doc_type == "QUY_CHUAN" else "legal",
            parser_version="qcvn-v1" if normalized_doc_type == "QUY_CHUAN" else "legal-v2",
            issuer=clean_issuer,
            source_url=source_url.strip() if source_url else None,
            domain_tags=parsed_tags,
            uploaded_by=current_user.user_id,
        )
        db_session.add(document)
        try:
            await db_session.flush()
        except IntegrityError as exc:
            if not _is_source_checksum_integrity_error(exc):
                await db_session.rollback()
                _remove_uploaded_source(saved_upload.storage_path)
                _remove_uploaded_source(stored_path)
                raise
            await db_session.rollback()
            _remove_uploaded_source(saved_upload.storage_path)
            _remove_uploaded_source(stored_path)
            duplicate = await _find_exact_duplicate_by_checksum(db_session, source_checksum)
            raise HTTPException(
                status_code=409,
                detail=_duplicate_source_detail(source_checksum, duplicate),
            ) from exc

        (
            chunk_count,
            parser_confidence,
            warnings,
            extracted_metadata,
            processing_error,
        ) = await _prepare_pending_chunks(
            db_session,
            document,
            stored_path,
        )
        warnings, extracted_metadata = _apply_duplicate_candidates(
            warnings,
            extracted_metadata
            | (
                {
                    "source_checksum": source_checksum,
                    "target_doc_id": target_document.doc_id,
                }
                if target_document is not None
                else {"source_checksum": source_checksum}
            ),
            duplicate_candidates,
        )
        queue = KbUpdateQueue(
            doc_id=document.doc_id,
            target_doc_id=target_document.doc_id if target_document is not None else None,
            change_type=change_type,
            review_status="pending",
            processing_status="failed" if processing_error else "ready",
            source_file_name=safe_name,
            source_path=saved_upload.storage_path,
            parser_confidence=parser_confidence,
            warning_messages=warnings,
            extracted_metadata=extracted_metadata
            | {"uploaded_file_name": safe_name, "chunk_count": chunk_count},
            processing_error=processing_error,
            created_by=current_user.user_id,
        )
        db_session.add(queue)
        await db_session.commit()
        await db_session.refresh(queue)
        await db_session.refresh(document)
        if saved_upload.storage_path != stored_path:
            _remove_uploaded_source(stored_path)

        return KbQueueDetailOut(
            queue_id=queue.queue_id,
            doc_id=document.doc_id,
            target_doc_id=queue.target_doc_id,
            change_type=queue.change_type,
            review_status=queue.review_status,
            processing_status=queue.processing_status,
            parser_confidence=queue.parser_confidence,
            warning_messages=list(queue.warning_messages or []),
            extracted_metadata=dict(queue.extracted_metadata or {}),
            review_checklist=dict(queue.review_checklist or {}),
            reviewer_draft_note=queue.reviewer_draft_note,
            reviewer_note=queue.reviewer_note,
            reject_reason=queue.reject_reason,
            processing_error=queue.processing_error,
            source_file_name=queue.source_file_name,
            created_at=queue.created_at,
            reviewed_at=queue.reviewed_at,
            document=_document_to_queue_doc(document),
            target_document=_document_to_queue_doc(target_document),
            chunks=[],
        )
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


@router.patch("/queue/{queue_id}/draft", response_model=KbQueueDetailOut)
async def save_kb_queue_draft(
    queue_id: str,
    payload: KbQueueDraftRequest,
    db_session: AsyncSession = Depends(get_session),
):
    try:
        queue = await db_session.scalar(
            select(KbUpdateQueue)
            .where(KbUpdateQueue.queue_id == queue_id)
            .options(
                selectinload(KbUpdateQueue.document).selectinload(LegalDocument.chunks),
                selectinload(KbUpdateQueue.document).selectinload(LegalDocument.assets),
                selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.chunks),
                selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.assets),
            )
        )
        if queue is None or queue.document is None:
            raise HTTPException(status_code=404, detail="Queue item not found")
        if queue.review_status != "pending":
            raise HTTPException(status_code=409, detail="Queue item is no longer editable")

        document = queue.document
        if payload.title is not None:
            document.title = payload.title.strip()
        if payload.issuer is not None:
            document.issuer = payload.issuer.strip()
        if payload.source_url is not None:
            document.source_url = payload.source_url.strip() or None
        if payload.effective_date is not None:
            document.effective_date = payload.effective_date
            for chunk in document.chunks:
                chunk.effective_date = payload.effective_date
        if payload.expiry_date is not None:
            if payload.expiry_date <= document.effective_date:
                raise HTTPException(
                    status_code=422,
                    detail="Ngày hết hiệu lực phải sau ngày có hiệu lực.",
                )
            document.expiry_date = payload.expiry_date
            document.valid_to = payload.expiry_date
            if queue.change_type == "repeal":
                metadata = dict(queue.extracted_metadata or {})
                metadata["expiry_date"] = payload.expiry_date.isoformat()
                queue.extracted_metadata = metadata
        if payload.domain_tags is not None:
            document.domain_tags = payload.domain_tags
        if payload.target_doc_id is not None:
            if queue.change_type not in {"update", "repeal"}:
                queue.target_doc_id = None
            else:
                target_document = await _resolve_upload_target_document(
                    db_session,
                    change_type=queue.change_type,
                    target_doc_id=payload.target_doc_id or queue.target_doc_id,
                    exclude_queue_id=queue.queue_id,
                )
                queue.target_doc_id = target_document.doc_id if target_document else None
        if payload.reviewer_draft_note is not None:
            queue.reviewer_draft_note = payload.reviewer_draft_note
        if payload.review_checklist is not None:
            queue.review_checklist = payload.review_checklist
        exclude_doc_id = document.doc_id
        exclude_target_doc_id = (
            queue.target_doc_id if queue.change_type in {"update", "repeal"} else None
        )
        if queue.change_type == "repeal":
            duplicate_candidates = []
        elif (
            _is_metadata_only_update(queue)
            and queue.target_document
            and _metadata_matches_document(document, queue.target_document)
        ):
            duplicate_candidates = []
        else:
            duplicate_candidates = await _find_duplicate_candidates(
                db_session,
                title=document.title,
                doc_type=document.doc_type,
                issuer=document.issuer,
                effective_date=document.effective_date,
                source_url=document.source_url,
                exclude_doc_id=exclude_target_doc_id or exclude_doc_id,
            )
            ignored_doc_ids = {exclude_doc_id}
            if exclude_target_doc_id:
                ignored_doc_ids.add(exclude_target_doc_id)
            duplicate_candidates = [
                candidate
                for candidate in duplicate_candidates
                if candidate["doc_id"] not in ignored_doc_ids
            ]
        queue.warning_messages, queue.extracted_metadata = _apply_duplicate_candidates(
            list(queue.warning_messages or []),
            dict(queue.extracted_metadata or {}),
            duplicate_candidates,
        )

        await db_session.commit()
        await db_session.refresh(queue)
        return await get_kb_queue_detail(queue_id, db_session)
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


def _set_approval_job_metadata(
    queue: KbUpdateQueue,
    *,
    status_value: str,
    step: str,
    message: str,
    error: str | None = None,
) -> None:
    metadata = dict(queue.extracted_metadata or {})
    metadata["approval_job"] = {
        "status": status_value,
        "step": step,
        "message": message,
        "error": error,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    queue.extracted_metadata = metadata


def _approval_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


def _reconcile_document_metadata(document: LegalDocument, queue: KbUpdateQueue) -> None:
    """Compatibility wrapper for legacy scripts/tests."""
    reconcile_legacy_document_metadata(document, queue)


async def _load_queue_for_approval(
    db_session: AsyncSession,
    queue_id: str,
) -> KbUpdateQueue:
    queue = await db_session.scalar(
        select(KbUpdateQueue)
        .where(KbUpdateQueue.queue_id == queue_id)
        .options(
            selectinload(KbUpdateQueue.document).selectinload(LegalDocument.chunks),
            selectinload(KbUpdateQueue.document).selectinload(LegalDocument.assets),
            selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.chunks),
            selectinload(KbUpdateQueue.target_document).selectinload(LegalDocument.assets),
        )
    )
    if queue is None or queue.document is None:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return queue


def _validate_queue_can_start_approval(queue: KbUpdateQueue, payload: KbQueueApproveRequest) -> str:
    if queue.review_status != "pending":
        raise HTTPException(status_code=409, detail="Queue item has already been reviewed")
    if queue.processing_status != "ready":
        approval_job = (queue.extracted_metadata or {}).get("approval_job")
        if not isinstance(approval_job, dict):
            approval_job = {}
        if queue.processing_status == "queued":
            if approval_job.get("status") == "running":
                raise HTTPException(status_code=409, detail="Queue item is already being approved")
        elif not (queue.processing_status == "failed" and approval_job.get("status") == "failed"):
            raise HTTPException(
                status_code=409,
                detail="Queue item is not ready for review and cannot be approved",
            )

    metadata_only_update = _is_metadata_only_update(queue)
    missing_embeddings = any(chunk.embedding_vector is None for chunk in queue.document.chunks)
    if queue.change_type != "repeal" and not metadata_only_update and missing_embeddings:
        raise HTTPException(
            status_code=409,
            detail="Queue item still has chunks without embeddings and cannot be approved",
        )
    missing_checks = sorted(
        key for key in _REQUIRED_REVIEW_CHECKS if queue.review_checklist.get(key) is not True
    )
    if missing_checks:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVIEW_CHECKLIST_INCOMPLETE",
                "missing": missing_checks,
            },
        )
    reviewer_note = (payload.reviewer_note or "").strip()
    if _reviewer_note_required_for_approval(queue) and not reviewer_note:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVIEWER_NOTE_REQUIRED",
                "message": "Reviewer note is required when approving a queue item with warnings or duplicate candidates.",
            },
        )
    return reviewer_note


async def _record_approval_failure(queue_id: str, exc: Exception) -> None:
    async with async_session_factory() as db_session:
        queue = await db_session.get(KbUpdateQueue, queue_id)
        if queue is None:
            return
        queue.processing_status = "failed"
        queue.processing_error = _approval_error_message(exc)
        _set_approval_job_metadata(
            queue,
            status_value="failed",
            step="failed",
            message="Khong the phe duyet ho so. Admin co the xem loi va thu lai.",
            error=queue.processing_error,
        )
        await db_session.commit()


async def _publish_approval_job(queue_id: str, payload: KbQueueApproveRequest) -> None:
    try:
        async with async_session_factory() as db_session:
            queue = await _load_queue_for_approval(db_session, queue_id)
            if queue.review_status != "pending":
                return

            reviewer_note = (payload.reviewer_note or "").strip()
            _set_approval_job_metadata(
                queue,
                status_value="running",
                step="publishing",
                message="Dang cap nhat Kho van ban va dong bo chi muc tra cuu.",
            )
            await db_session.commit()

            queue = await _load_queue_for_approval(db_session, queue_id)
            metadata_only_update = _is_metadata_only_update(queue)
            queue.review_status = "approved"
            queue.processing_status = "ready"
            queue.processing_error = None
            queue.reviewer_note = reviewer_note
            queue.reviewed_by = payload.reviewed_by
            queue.reviewed_at = datetime.now(tz=UTC)

            document = queue.document
            target_document = queue.target_document or (
                await db_session.get(LegalDocument, queue.target_doc_id)
                if queue.target_doc_id
                else None
            )

            publish_document = document
            staging_document: LegalDocument | None = None
            source_checksum = (queue.extracted_metadata or {}).get("source_checksum")

            if queue.change_type == "update":
                if target_document is None:
                    raise HTTPException(
                        status_code=409, detail="Queue item is missing target document"
                    )
                staging_document = document
                publish_document = target_document
                if (
                    not metadata_only_update
                    and isinstance(source_checksum, str)
                    and source_checksum
                ):
                    duplicate = await _find_exact_duplicate_by_checksum(
                        db_session,
                        source_checksum,
                        exclude_doc_id=publish_document.doc_id,
                    )
                    if duplicate is not None:
                        raise HTTPException(
                            status_code=409,
                            detail=_duplicate_source_detail(source_checksum, duplicate),
                        )

                publish_document.title = staging_document.title
                publish_document.doc_type = staging_document.doc_type
                publish_document.document_number = staging_document.document_number
                publish_document.document_family = staging_document.document_family
                publish_document.issuer = staging_document.issuer
                publish_document.source_url = staging_document.source_url
                publish_document.domain_tags = list(staging_document.domain_tags or [])
                publish_document.effective_date = staging_document.effective_date
                publish_document.expiry_date = staging_document.expiry_date
                publish_document.valid_from = (
                    staging_document.valid_from or staging_document.effective_date
                )
                publish_document.valid_to = (
                    staging_document.valid_to or staging_document.expiry_date
                )
                publish_document.parser_profile = staging_document.parser_profile
                publish_document.parser_version = staging_document.parser_version
                publish_document.index_version = staging_document.index_version
                publish_document.rag_scope = staging_document.rag_scope
                publish_document.rag_enabled = staging_document.rag_enabled
                publish_document.legal_status = staging_document.legal_status
                if (
                    not metadata_only_update
                    and isinstance(source_checksum, str)
                    and source_checksum
                ):
                    publish_document.source_checksum = source_checksum

                if not metadata_only_update:
                    publish_document.source_version = int(publish_document.source_version or 1) + 1
                    for chunk in list(publish_document.chunks):
                        await db_session.delete(chunk)
                    for asset in list(publish_document.assets):
                        await db_session.delete(asset)
                    await db_session.flush()

                    for chunk in list(staging_document.chunks):
                        chunk.document = publish_document
                    for asset in list(staging_document.assets):
                        asset.document = publish_document

                queue.document = publish_document
                document = publish_document

            elif queue.change_type == "repeal":
                if target_document is None:
                    raise HTTPException(
                        status_code=409, detail="Queue item is missing target document"
                    )
                staging_document = document
                publish_document = target_document
                expiry_on = staging_document.expiry_date or staging_document.valid_to
                if expiry_on is None:
                    raise HTTPException(status_code=409, detail="Queue item is missing expiry date")
                if expiry_on <= publish_document.effective_date:
                    raise HTTPException(
                        status_code=409,
                        detail="Ngày hết hiệu lực phải sau ngày có hiệu lực.",
                    )
                replacement_id = (queue.extracted_metadata or {}).get("replaced_by_id")
                if replacement_id:
                    replacement = await db_session.get(LegalDocument, replacement_id)
                    if (
                        replacement is None
                        or replacement.review_status != "approved"
                        or replacement.status == "repealed"
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail="Văn bản thay thế không tồn tại, chưa được duyệt hoặc đã hết hiệu lực.",
                        )
                publish_document.expiry_date = expiry_on
                publish_document.valid_to = expiry_on
                publish_document.replaced_by_id = replacement_id or None
                queue.document = publish_document
                document = publish_document

            _reconcile_document_metadata(document, queue)
            previous_status = document.status
            previous_legal_status = document.legal_status
            document.review_status = "approved"
            apply_current_state(document, as_of=current_legal_date())
            if document.status == "repealed" and previous_status != "repealed":
                db_session.add(
                    DocumentLifecycleEvent(
                        doc_id=document.doc_id,
                        event_type=(
                            "repeal_approved"
                            if queue.change_type == "repeal"
                            else "expired_on_approval"
                        ),
                        source="hitl_approval",
                        effective_on=document_expiry_on(document) or current_legal_date(),
                        previous_status=previous_status,
                        previous_legal_status=previous_legal_status,
                        new_status=document.status,
                        new_legal_status=document.legal_status,
                        details={"queue_id": queue.queue_id},
                    )
                )
            elif queue.change_type == "repeal":
                db_session.add(
                    DocumentLifecycleEvent(
                        doc_id=document.doc_id,
                        event_type="repeal_scheduled",
                        source="hitl_approval",
                        effective_on=document_expiry_on(document) or current_legal_date(),
                        previous_status=previous_status,
                        previous_legal_status=previous_legal_status,
                        new_status=document.status,
                        new_legal_status=document.legal_status,
                        details={"queue_id": queue.queue_id},
                    )
                )

            if staging_document is not None:
                await db_session.flush()
                await db_session.delete(staging_document)

            _set_approval_job_metadata(
                queue,
                status_value="succeeded",
                step="completed",
                message="Ho so da duoc phe duyet va cap nhat vao Kho van ban.",
            )
            notification = await create_approval_notification(
                db_session,
                document=document,
                queue=queue,
            )
            try:
                await db_session.commit()
                await db_session.refresh(notification)
                try:
                    await publish_notification(notification)
                except Exception:
                    logger.warning(
                        "Failed to broadcast notification %s",
                        notification.notification_id,
                        exc_info=True,
                    )
            except IntegrityError as exc:
                await db_session.rollback()
                if not _is_source_checksum_integrity_error(exc):
                    raise
                duplicate = (
                    await _find_exact_duplicate_by_checksum(db_session, source_checksum)
                    if isinstance(source_checksum, str) and source_checksum
                    else None
                )
                raise HTTPException(
                    status_code=409,
                    detail=_duplicate_source_detail(source_checksum, duplicate),
                ) from exc
    except Exception as exc:
        await _record_approval_failure(queue_id, exc)


@router.post("/queue/{queue_id}/approve", response_model=KbQueueDetailOut)
async def start_kb_queue_approval(
    queue_id: str,
    payload: KbQueueApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    try:
        payload = payload.model_copy(update={"reviewed_by": current_user.user_id})
        queue = await _load_queue_for_approval(db_session, queue_id)
        _validate_queue_can_start_approval(queue, payload)

        queue.processing_status = "queued"
        queue.processing_error = None
        _set_approval_job_metadata(
            queue,
            status_value="running",
            step="queued",
            message="Da nhan lenh phe duyet. He thong se xu ly nen va cap nhat tien trinh.",
        )
        await db_session.commit()

        background_tasks.add_task(_publish_approval_job, queue_id, payload)
        return await get_kb_queue_detail(queue_id, db_session)
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise


async def approve_kb_queue_item(
    queue_id: str,
    payload: KbQueueApproveRequest,
    db_session: AsyncSession,
):
    queue = await _load_queue_for_approval(db_session, queue_id)
    _validate_queue_can_start_approval(queue, payload)
    queue.processing_status = "queued"
    queue.processing_error = None
    _set_approval_job_metadata(
        queue,
        status_value="running",
        step="queued",
        message="Da nhan lenh phe duyet. He thong se xu ly nen va cap nhat tien trinh.",
    )
    await db_session.commit()
    return await get_kb_queue_detail(queue_id, db_session)


@router.post("/queue/{queue_id}/reject", response_model=KbQueueDetailOut)
async def reject_kb_queue_item(
    queue_id: str,
    payload: KbQueueRejectRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    try:
        if payload.reject_reason not in _REJECT_REASONS:
            raise HTTPException(status_code=422, detail="Unsupported reject_reason")

        queue = await db_session.scalar(
            select(KbUpdateQueue)
            .where(KbUpdateQueue.queue_id == queue_id)
            .options(
                selectinload(KbUpdateQueue.document).selectinload(LegalDocument.chunks),
                selectinload(KbUpdateQueue.target_document),
            )
        )
        if queue is None or queue.document is None:
            raise HTTPException(status_code=404, detail="Queue item not found")
        if queue.review_status != "pending":
            raise HTTPException(status_code=409, detail="Queue item has already been reviewed")
        approval_job = (queue.extracted_metadata or {}).get("approval_job")
        if (
            queue.processing_status == "queued"
            and isinstance(approval_job, dict)
            and approval_job.get("status") == "running"
        ):
            raise HTTPException(status_code=409, detail="Queue item is already being approved")

        queue.review_status = "rejected"
        queue.document.review_status = "rejected"
        queue.reject_reason = payload.reject_reason
        queue.reviewer_note = (payload.reviewer_note or "").strip() or _REJECT_REASON_LABELS[
            payload.reject_reason
        ]
        queue.reviewed_by = current_user.user_id
        queue.reviewed_at = datetime.now(tz=UTC)
        await db_session.commit()
        return await get_kb_queue_detail(queue_id, db_session)
    except Exception as exc:
        if _is_schema_outdated_error(exc):
            _raise_schema_outdated(exc)
        raise
