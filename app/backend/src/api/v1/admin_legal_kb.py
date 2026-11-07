from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas import (
    LegalKbNodeOut,
    LegalKbDocumentOut,
    LegalKbRelationOut,
    LegalKbMetadataProposalCreateRequest,
    LegalKbMetadataProposalOut,
    LegalKbNodeResetReviewRequest,
    LegalKbNodeReviewRequest,
    LegalKbProposalReviewRequest,
    LegalKbPublishedDocumentListItemOut,
    LegalKbPublishedDocumentListResponse,
    LegalKbPublishedDocumentStatusRequest,
    LegalKbPublishedDocumentUpdateRequest,
    LegalKbRelationCreateRequest,
    LegalKbRelationReviewRequest,
    LegalKbRelationTargetItemOut,
    LegalKbRelationTargetListResponse,
    LegalKbRelationUpdateRequest,
    LegalKbRetrievalUnitOut,
    LegalKbReviewEventOut,
    LegalKbRevisionDetailResponse,
    LegalKbRevisionListItemOut,
    LegalKbRevisionListResponse,
    LegalKbRevisionOut,
    LegalKbRevisionSourceUpdateRequest,
    LegalKbRiskyNodeBulkReviewRequest,
    LegalKbSourceAssetOut,
    LegalKbSummaryOut,
    LegalKbSummaryReviewRequest,
    LegalKbSuspendRequest,
    LegalKbUploadResponse,
)
from src.auth.dependencies import require_admin
from src.core.config import settings
from src.db.session import get_session
from src.legal_kb.ingestion import LegalKbIngestionResult, ingest_legal_kb_docx
from src.legal_kb.metadata import normalize_document_role, normalize_document_type
from src.legal_kb.publication import (
    _published_legal_status,
    collect_publish_blockers,
    publish_revision,
    suspend_revision,
    unsuspend_revision,
)
from src.legal_kb.review import (
    bulk_review_risky_nodes,
    create_metadata_proposal,
    create_relation_proposal,
    delete_relation,
    load_revision_bundle,
    normalize_legacy_revision_review_state,
    relation_review_status,
    reset_canonical_node_review,
    review_canonical_node,
    review_metadata_proposal,
    review_relation,
    review_summary,
    update_relation_proposal,
)
from src.models.legal_kb import (
    LegalKbRelation,
    LegalKbRevision,
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbReviewEvent,
    LegalKbSourceAsset,
    LegalKbSummary,
)
from src.models.user import User
from src.storage.object_storage import get_object_storage, is_object_uri

router = APIRouter(prefix="/admin/legal-kb", tags=["admin-legal-kb"], dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)


def _ensure_legal_kb_enabled() -> None:
    """Compat shim after KB cutover: admin KB routes are always available."""
    return None


def _legal_kb_runtime_http_error(exc: SQLAlchemyError) -> HTTPException:
    raw_message = str(getattr(exc, "orig", exc))
    normalized = raw_message.lower()
    if isinstance(exc, OperationalError) or "connection refused" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_UNAVAILABLE",
                "message": "Không kết nối được PostgreSQL. Hãy khởi động database và kiểm tra DATABASE_URL.",
            },
        )
    if isinstance(exc, ProgrammingError) or "undefinedtable" in normalized or "does not exist" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_SCHEMA_NOT_READY",
                "message": "Cấu trúc dữ liệu mới chưa sẵn sàng. Hãy chạy migration tới bản mới nhất trước khi tải lên hoặc duyệt văn bản.",
            },
        )
    if isinstance(exc, DBAPIError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_ERROR",
                "message": "Database trả lỗi khi xử lý kho văn bản. Kiểm tra log backend để xem chi tiết.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "KB_INTERNAL_ERROR",
            "message": "Không thể xử lý yêu cầu này vào lúc này.",
        },
    )


def _legal_kb_list_runtime_http_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "KB_DOCUMENT_LIST_UNAVAILABLE",
            "message": "Hệ thống chưa thể tải danh sách văn bản trong kho. Vui lòng thử lại sau.",
        },
    )

def _legal_kb_revision_list_http_error(exc: SQLAlchemyError | None = None) -> HTTPException:
    if exc is None:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "KB_DOCUMENT_LIST_UNAVAILABLE",
                "message": "Hệ thống chưa thể tải danh sách hồ sơ duyệt văn bản. Vui lòng thử lại sau.",
            },
        )

    raw_message = str(getattr(exc, "orig", exc))
    normalized = raw_message.lower()
    if isinstance(exc, OperationalError) or "connection refused" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_UNAVAILABLE",
                "message": "Không kết nối được PostgreSQL. Hãy khởi động database và kiểm tra DATABASE_URL.",
            },
        )
    if isinstance(exc, ProgrammingError) or "undefinedtable" in normalized or "does not exist" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_SCHEMA_NOT_READY",
                "message": "Cấu trúc dữ liệu mới chưa sẵn sàng. Hãy chạy migration tới bản mới nhất trước khi duyệt văn bản.",
            },
        )
    if isinstance(exc, DBAPIError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_ERROR",
                "message": "Database trả lỗi khi tải danh sách hồ sơ duyệt văn bản. Kiểm tra log backend để xem chi tiết.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "KB_DOCUMENT_LIST_UNAVAILABLE",
            "message": "Hệ thống chưa thể tải danh sách hồ sơ duyệt văn bản. Vui lòng thử lại sau.",
        },
    )


def _legal_kb_revision_detail_http_error(exc: SQLAlchemyError | None = None) -> HTTPException:
    if exc is None:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "KB_REVISION_DETAIL_UNAVAILABLE",
                "message": "Chưa thể mở chi tiết hồ sơ xử lý này. Vui lòng thử lại sau.",
            },
        )

    raw_message = str(getattr(exc, "orig", exc))
    normalized = raw_message.lower()
    if isinstance(exc, OperationalError) or "connection refused" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_UNAVAILABLE",
                "message": "Không kết nối được PostgreSQL. Hãy khởi động database và kiểm tra DATABASE_URL.",
            },
        )
    if isinstance(exc, ProgrammingError) or "undefinedtable" in normalized or "does not exist" in normalized:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_SCHEMA_NOT_READY",
                "message": "Cấu trúc dữ liệu mới chưa sẵn sàng. Hãy chạy migration tới bản mới nhất trước khi mở hồ sơ duyệt văn bản.",
            },
        )
    if isinstance(exc, DBAPIError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KB_DATABASE_ERROR",
                "message": "Database trả lỗi khi mở chi tiết hồ sơ xử lý. Kiểm tra log backend để xem chi tiết.",
            },
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "KB_REVISION_DETAIL_UNAVAILABLE",
            "message": "Chưa thể mở chi tiết hồ sơ xử lý này. Vui lòng thử lại sau.",
        },
    )


@router.post("/revisions/upload", response_model=LegalKbUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_legal_kb_revision(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=3, max_length=500),
    source_url: str = Form(..., min_length=5, max_length=1000),
    source_downloaded_at: str = Form(...),
    source_note: str = Form(..., min_length=3, max_length=5000),
    document_number: str | None = Form(default=None, max_length=120),
    document_type: str | None = Form(default=None, max_length=40),
    document_role: str | None = Form(default=None, max_length=40),
    issuing_authority: str | None = Form(default=None, max_length=255),
    issued_date: str | None = Form(default=None),
    effective_date: str | None = Form(default=None),
    expiry_date: str | None = Form(default=None),
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    try:
        result = await ingest_legal_kb_docx(
            db_session,
            file=file,
            title=title,
            source_url=source_url,
            source_downloaded_at=_parse_iso_date(source_downloaded_at, field_name="source_downloaded_at"),
            source_note=source_note,
            document_number=document_number,
            document_type=document_type,
            document_role=document_role,
            issuing_authority=issuing_authority,
            issued_date=_parse_optional_iso_date(issued_date, field_name="issued_date"),
            effective_date=_parse_optional_iso_date(effective_date, field_name="effective_date"),
            expiry_date=_parse_optional_iso_date(expiry_date, field_name="expiry_date"),
            uploaded_by=current_user.user_id,
        )
    except SQLAlchemyError as exc:
        logger.exception("kho văn bản upload failed with a database error")
        raise _legal_kb_runtime_http_error(exc) from exc
    return _serialize_upload_response(result)


@router.post(
    "/documents/{document_id}/replacement-revisions/upload",
    response_model=LegalKbUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_legal_kb_replacement_revision(
    document_id: str,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=3, max_length=500),
    source_url: str = Form(..., min_length=5, max_length=1000),
    source_downloaded_at: str = Form(...),
    source_note: str = Form(..., min_length=3, max_length=5000),
    document_number: str | None = Form(default=None, max_length=120),
    document_type: str | None = Form(default=None, max_length=40),
    document_role: str | None = Form(default=None, max_length=40),
    issuing_authority: str | None = Form(default=None, max_length=255),
    issued_date: str | None = Form(default=None),
    effective_date: str | None = Form(default=None),
    expiry_date: str | None = Form(default=None),
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    document = await db_session.scalar(
        select(LegalKbDocument)
        .where(LegalKbDocument.document_id == document_id)
        .options(selectinload(LegalKbDocument.revisions))
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KB_DOCUMENT_NOT_FOUND", "message": "Không tìm thấy văn bản cần thay file nguồn."},
        )
    current_revision = _current_repository_revision(document)
    if current_revision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "KB_REPLACEMENT_REQUIRES_MANAGED_DOCUMENT",
                "message": "Chỉ có thể thay file nguồn cho văn bản đã hoặc từng được đưa vào kho.",
            },
        )
    try:
        result = await ingest_legal_kb_docx(
            db_session,
            file=file,
            title=title,
            source_url=source_url,
            source_downloaded_at=_parse_iso_date(source_downloaded_at, field_name="source_downloaded_at"),
            source_note=source_note,
            document_number=document_number,
            document_type=document_type,
            document_role=document_role,
            issuing_authority=issuing_authority,
            issued_date=_parse_optional_iso_date(issued_date, field_name="issued_date"),
            effective_date=_parse_optional_iso_date(effective_date, field_name="effective_date"),
            expiry_date=_parse_optional_iso_date(expiry_date, field_name="expiry_date"),
            uploaded_by=current_user.user_id,
            existing_document=document,
        )
    except SQLAlchemyError as exc:
        logger.exception("kho văn bản replacement upload failed with a database error")
        raise _legal_kb_runtime_http_error(exc) from exc
    return _serialize_upload_response(result)


@router.get("/revisions", response_model=LegalKbRevisionListResponse)
async def list_legal_kb_revisions(
    q: str | None = None,
    publication_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    try:
        query = (
            select(LegalKbRevision, LegalKbSourceAsset.original_filename)
            .join(LegalKbRevision.document)
            .outerjoin(LegalKbRevision.source_asset)
            .options(
                selectinload(LegalKbRevision.document).selectinload(LegalKbDocument.outgoing_relations),
                selectinload(LegalKbRevision.document).selectinload(LegalKbDocument.incoming_relations),
                selectinload(LegalKbRevision.source_asset),
                selectinload(LegalKbRevision.source_assets),
                selectinload(LegalKbRevision.metadata_proposals),
                selectinload(LegalKbRevision.standard_summaries),
                selectinload(LegalKbRevision.canonical_nodes),
                selectinload(LegalKbRevision.review_events),
            )
        )
        if q:
            term = f"%{q.strip()}%"
            query = query.where(
                or_(
                    LegalKbDocument.title.ilike(term),
                    LegalKbDocument.document_number.ilike(term),
                )
            )
        if publication_status:
            query = query.where(LegalKbRevision.publication_status == publication_status.strip())

        count_result = await db_session.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0
        rows = (
            await db_session.execute(
                query.order_by(LegalKbRevision.uploaded_at.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        items = [
            _serialize_revision_list_item(revision=revision, source_file_name=source_file_name)
            for revision, source_file_name in rows
        ]
    except SQLAlchemyError as exc:
        logger.exception("kho văn bản revision listing failed with a database error")
        raise _legal_kb_revision_list_http_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kho văn bản revision listing failed unexpectedly")
        raise _legal_kb_revision_list_http_error() from exc
    return LegalKbRevisionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/revisions/{revision_id}", response_model=LegalKbRevisionDetailResponse)
async def get_legal_kb_revision_detail(
    revision_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    try:
        bundle = await load_revision_bundle(db_session, revision_id)
        if normalize_legacy_revision_review_state(bundle):
            await db_session.commit()
        return _serialize_revision_detail(bundle)
    except SQLAlchemyError as exc:
        logger.exception("kho văn bản revision detail failed with a database error")
        raise _legal_kb_revision_detail_http_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kho văn bản revision detail failed unexpectedly")
        raise _legal_kb_revision_detail_http_error() from exc


@router.get("/revisions/{revision_id}/source")
async def download_legal_kb_revision_source(
    revision_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await load_revision_bundle(db_session, revision_id)
    if bundle.source_asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tệp nguồn của văn bản này.",
    )
    return _serve_source_asset(bundle.source_asset)


@router.patch("/revisions/{revision_id}/source", response_model=LegalKbRevisionDetailResponse)
async def update_legal_kb_revision_source(
    revision_id: str,
    payload: LegalKbRevisionSourceUpdateRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await load_revision_bundle(db_session, revision_id)
    updates = payload.model_dump(exclude_unset=True)
    _apply_revision_source_updates(bundle.revision, bundle.source_asset, updates)
    if updates:
        db_session.add(
            LegalKbReviewEvent(
                review_event_id=str(uuid4()),
                document_id=bundle.document.document_id,
                revision_id=bundle.revision.revision_id,
                entity_type="revision",
                entity_id=bundle.revision.revision_id,
                decision="updated",
                actor_user_id=current_user.user_id,
                details={"fields": sorted(updates.keys())},
            )
        )
    await db_session.commit()
    refreshed = await load_revision_bundle(db_session, revision_id)
    return _serialize_revision_detail(refreshed)


@router.get("/documents", response_model=LegalKbPublishedDocumentListResponse)
async def list_legal_kb_documents(
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    try:
        rows = await db_session.execute(
            select(LegalKbDocument)
            .options(
                selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.source_asset),
                selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.standard_summaries),
                selectinload(LegalKbDocument.source_assets),
                selectinload(LegalKbDocument.outgoing_relations),
                selectinload(LegalKbDocument.incoming_relations),
            )
            .order_by(LegalKbDocument.updated_at.desc(), LegalKbDocument.created_at.desc())
        )
        normalized_query = (q or "").strip().lower()
        normalized_status = (status or "").strip().lower()
        items: list[LegalKbPublishedDocumentListItemOut] = []
        for document in rows.scalars().unique():
            bundle = _managed_bundle_from_document(document)
            if bundle is None:
                continue
            if normalized_query and not _document_matches_query(document, normalized_query):
                continue
            display_status = _display_status_for_bundle(bundle)
            if normalized_status and display_status != normalized_status:
                continue
            items.append(
                LegalKbPublishedDocumentListItemOut(
                    document_id=document.document_id,
                    revision_id=bundle.revision.revision_id,
                    title=document.title,
                    document_number=document.document_number,
                    document_type=document.document_type,
                    issuing_authority=document.issuing_authority,
                    effective_date=document.effective_date,
                    expiry_date=document.expiry_date,
                    legal_status=document.legal_status,
                    publication_status=bundle.revision.publication_status,
                    display_status=display_status,
                    source_file_name=bundle.source_asset.original_filename if bundle.source_asset else None,
                    updated_at=document.updated_at,
                    relation_count=len(bundle.relations),
                )
            )

        total = len(items)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return LegalKbPublishedDocumentListResponse(
            items=items[start:end],
            total=total,
            page=page,
            page_size=page_size,
        )
    except SQLAlchemyError as exc:
        logger.exception("kho văn bản published document listing failed with a database error")
        raise _legal_kb_runtime_http_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("kho văn bản published document listing failed unexpectedly")
        raise _legal_kb_list_runtime_http_error() from exc


@router.get("/relation-targets", response_model=LegalKbRelationTargetListResponse)
async def list_legal_kb_relation_targets(
    q: str | None = None,
    exclude_document_id: str | None = None,
    limit: int = 50,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    normalized_query = (q or "").strip().lower()
    filters = []
    if exclude_document_id:
        filters.append(LegalKbDocument.document_id != exclude_document_id)
    if normalized_query:
        pattern = f"%{normalized_query}%"
        filters.append(
            or_(
                func.lower(cast(LegalKbDocument.document_id, String)).like(pattern),
                func.lower(func.coalesce(LegalKbDocument.document_number, "")).like(pattern),
                func.lower(func.coalesce(LegalKbDocument.title, "")).like(pattern),
            )
        )

    safe_limit = min(max(limit, 1), 100)
    count_statement = select(func.count()).select_from(LegalKbDocument)
    list_statement = select(LegalKbDocument)
    if filters:
        count_statement = count_statement.where(*filters)
        list_statement = list_statement.where(*filters)
    total = int((await db_session.execute(count_statement)).scalar() or 0)
    rows = await db_session.execute(
        list_statement
        .order_by(LegalKbDocument.updated_at.desc(), LegalKbDocument.created_at.desc())
        .limit(safe_limit)
    )
    return LegalKbRelationTargetListResponse(
        items=[
            LegalKbRelationTargetItemOut(
                document_id=document.document_id,
                title=document.title,
                document_number=document.document_number,
            )
            for document in rows.scalars().all()
        ],
        total=total,
    )


@router.get("/documents/{document_id}", response_model=LegalKbRevisionDetailResponse)
async def get_legal_kb_document_detail(
    document_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await _load_managed_document_bundle(db_session, document_id)
    if normalize_legacy_revision_review_state(bundle):
        await db_session.commit()
    return _serialize_revision_detail(bundle)


@router.patch("/documents/{document_id}", response_model=LegalKbRevisionDetailResponse)
async def update_legal_kb_document(
    document_id: str,
    payload: LegalKbPublishedDocumentUpdateRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await _load_managed_document_bundle(db_session, document_id)
    updates = payload.model_dump(exclude_unset=True)
    document = bundle.document
    revision = bundle.revision
    source_asset = bundle.source_asset

    if "document_type" in updates:
        updates["document_type"] = normalize_document_type(updates["document_type"])

    for field_name in ("title", "document_number", "document_type", "issuing_authority", "issued_date", "effective_date", "expiry_date"):
        if field_name in updates:
            setattr(document, field_name, updates[field_name])

    if "document_role" in updates:
        metadata = dict(document.metadata_json or {})
        metadata["document_role"] = normalize_document_role(updates["document_role"])
        document.metadata_json = metadata

    _apply_revision_source_updates(revision, source_asset, updates)

    if any(key in updates for key in ("effective_date", "expiry_date")):
        if document.legal_status != "suspended":
            document.legal_status = _published_legal_status(document)
        _refresh_retrieval_units(bundle)

        db_session.add(
            LegalKbReviewEvent(
                review_event_id=str(uuid4()),
            document_id=document.document_id,
            revision_id=revision.revision_id,
            entity_type="document",
            entity_id=document.document_id,
            decision="updated",
            actor_user_id=current_user.user_id,
            details={"fields": sorted(updates.keys())},
        )
    )
    await db_session.commit()
    refreshed = await _load_managed_document_bundle(db_session, document_id)
    return _serialize_revision_detail(refreshed)


@router.post("/documents/{document_id}/status", response_model=LegalKbRevisionDetailResponse)
async def update_legal_kb_document_status(
    document_id: str,
    payload: LegalKbPublishedDocumentStatusRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await _load_managed_document_bundle(db_session, document_id)

    if payload.status == "suspended":
        await suspend_revision(
            db_session,
            revision_id=bundle.revision.revision_id,
            actor_user_id=current_user.user_id,
            reason=(payload.note or "Tạm ngừng để kiểm tra lại").strip(),
        )
        refreshed = await _load_managed_document_bundle(db_session, document_id)
        return _serialize_revision_detail(refreshed)

    document = bundle.document
    revision = bundle.revision
    metadata = dict(document.metadata_json or {})
    if payload.status == "active":
        revision.publication_status = "published"
        document.legal_status = _published_legal_status(document)
        metadata.pop("lifecycle_label", None)
        metadata.pop("replacement_document_id", None)
    else:
        revision.publication_status = "published"
        document.legal_status = "expired"
        metadata["lifecycle_label"] = payload.status
        if payload.replacement_document_id:
            metadata["replacement_document_id"] = payload.replacement_document_id
        else:
            metadata.pop("replacement_document_id", None)
    document.metadata_json = metadata
    _refresh_retrieval_units(bundle)
    db_session.add(
        LegalKbReviewEvent(
            review_event_id=str(uuid4()),
            document_id=document.document_id,
            revision_id=revision.revision_id,
            entity_type="document",
            entity_id=document.document_id,
            decision="updated",
            actor_user_id=current_user.user_id,
            details={
                "status": payload.status,
                "note": (payload.note or "").strip() or None,
                "replacement_document_id": payload.replacement_document_id,
            },
        )
    )
    await db_session.commit()
    refreshed = await _load_managed_document_bundle(db_session, document_id)
    return _serialize_revision_detail(refreshed)


@router.post("/revisions/{revision_id}/metadata-proposals", response_model=LegalKbMetadataProposalOut)
async def create_legal_kb_metadata_proposal(
    revision_id: str,
    payload: LegalKbMetadataProposalCreateRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    proposal = await create_metadata_proposal(
        db_session,
        revision_id=revision_id,
        field_name=payload.field_name,
        proposed_value=payload.proposed_value,
        actor_user_id=current_user.user_id,
        note=payload.note,
    )
    return _serialize_metadata_proposal(proposal)


@router.post("/metadata-proposals/{proposal_id}/review", response_model=LegalKbMetadataProposalOut)
async def review_legal_kb_metadata_proposal(
    proposal_id: str,
    payload: LegalKbProposalReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    proposal = await review_metadata_proposal(
        db_session,
        proposal_id=proposal_id,
        decision=payload.decision,
        actor_user_id=current_user.user_id,
        note=payload.note,
        proposed_value=payload.proposed_value,
    )
    return _serialize_metadata_proposal(proposal)


@router.post("/nodes/{node_id}/review", response_model=LegalKbNodeOut)
async def review_legal_kb_node(
    node_id: str,
    payload: LegalKbNodeReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    node = await review_canonical_node(
        db_session,
        node_id=node_id,
        decision=payload.decision,
        actor_user_id=current_user.user_id,
        note=payload.note,
        answerable=payload.answerable,
    )
    return _serialize_node(node)


@router.post("/nodes/{node_id}/reset-review", response_model=LegalKbNodeOut)
async def reset_legal_kb_node_review(
    node_id: str,
    payload: LegalKbNodeResetReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    node = await reset_canonical_node_review(
        db_session,
        node_id=node_id,
        actor_user_id=current_user.user_id,
        note=payload.note,
    )
    return _serialize_node(node)


@router.post("/revisions/{revision_id}/risky-nodes/bulk-review", response_model=LegalKbRevisionDetailResponse)
async def bulk_review_legal_kb_risky_nodes(
    revision_id: str,
    payload: LegalKbRiskyNodeBulkReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    bundle = await bulk_review_risky_nodes(
        db_session,
        revision_id=revision_id,
        node_type=payload.node_type,
        mode=payload.mode,
        actor_user_id=current_user.user_id,
        note=payload.note,
    )
    return _serialize_revision_detail(bundle)


@router.post("/revisions/{revision_id}/relations", response_model=LegalKbRelationOut)
async def create_legal_kb_relation_proposal(
    revision_id: str,
    payload: LegalKbRelationCreateRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    relation = await create_relation_proposal(
        db_session,
        revision_id=revision_id,
        target_document_id=payload.target_document_id,
        relation_type=payload.relation_type,
        actor_user_id=current_user.user_id,
        source_locator=payload.source_locator,
        target_locator=payload.target_locator,
        note=payload.note,
    )
    return _serialize_relation(relation)


@router.post("/relations/{relation_id}/review", response_model=LegalKbRelationOut)
async def review_legal_kb_relation(
    relation_id: str,
    payload: LegalKbRelationReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    relation = await review_relation(
        db_session,
        relation_id=relation_id,
        decision=payload.decision,
        actor_user_id=current_user.user_id,
        note=payload.note,
    )
    return _serialize_relation(relation)


@router.patch("/relations/{relation_id}", response_model=LegalKbRelationOut)
async def update_legal_kb_relation(
    relation_id: str,
    payload: LegalKbRelationUpdateRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    relation = await update_relation_proposal(
        db_session,
        relation_id=relation_id,
        actor_user_id=current_user.user_id,
        target_document_id=payload.target_document_id,
        relation_type=payload.relation_type,
        source_locator=payload.source_locator,
        target_locator=payload.target_locator,
        note=payload.note,
    )
    return _serialize_relation(relation)


@router.delete("/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_legal_kb_relation(
    relation_id: str,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    await delete_relation(
        db_session,
        relation_id=relation_id,
        actor_user_id=current_user.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/summaries/{summary_id}/review", response_model=LegalKbSummaryOut)
async def review_legal_kb_summary(
    summary_id: str,
    payload: LegalKbSummaryReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    summary = await review_summary(
        db_session,
        summary_id=summary_id,
        decision=payload.decision,
        actor_user_id=current_user.user_id,
        content=payload.content,
    )
    return _serialize_summary(summary)


@router.post("/revisions/{revision_id}/publish", response_model=LegalKbRevisionDetailResponse)
async def publish_legal_kb_revision(
    revision_id: str,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    await publish_revision(db_session, revision_id=revision_id, actor_user_id=current_user.user_id)
    bundle = await load_revision_bundle(db_session, revision_id)
    return _serialize_revision_detail(bundle)


@router.post("/revisions/{revision_id}/suspend", response_model=LegalKbRevisionDetailResponse)
async def suspend_legal_kb_revision(
    revision_id: str,
    payload: LegalKbSuspendRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    await suspend_revision(
        db_session,
        revision_id=revision_id,
        actor_user_id=current_user.user_id,
        reason=payload.reason,
    )
    bundle = await load_revision_bundle(db_session, revision_id)
    return _serialize_revision_detail(bundle)


@router.post("/revisions/{revision_id}/unsuspend", response_model=LegalKbRevisionDetailResponse)
async def unsuspend_legal_kb_revision(
    revision_id: str,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_enabled()
    await unsuspend_revision(
        db_session,
        revision_id=revision_id,
        actor_user_id=current_user.user_id,
    )
    bundle = await load_revision_bundle(db_session, revision_id)
    return _serialize_revision_detail(bundle)


def _serialize_upload_response(result: LegalKbIngestionResult) -> LegalKbUploadResponse:
    return LegalKbUploadResponse(
        document=_serialize_document(result.document),
        revision=_serialize_revision(result.revision),
        source_asset=_serialize_source_asset(result.source_asset),
        parser_confidence=result.parser_confidence,
        parser_warnings=result.parser_warnings,
        canonical_nodes=[_serialize_node(node) for node in result.canonical_nodes],
    )


def _serialize_revision_detail(bundle) -> LegalKbRevisionDetailResponse:
    canonical_nodes = [
        _serialize_node(node)
        for node in sorted(bundle.revision.canonical_nodes, key=lambda item: item.order_index)
    ]
    metadata_proposals = [
        _serialize_metadata_proposal(proposal)
        for proposal in sorted(
            bundle.revision.metadata_proposals,
            key=lambda item: (item.field_name, item.created_at.isoformat() if item.created_at else ""),
        )
    ]
    relations = [_serialize_relation(relation) for relation in bundle.relations]
    publish_blockers = collect_publish_blockers(bundle)
    pending_metadata = [proposal for proposal in metadata_proposals if proposal.review_status != "approved"]
    pending_relations = [
        relation
        for relation in relations
        if relation.source_document_id == bundle.document.document_id
        and relation.review_status != "approved"
    ]
    risky_nodes = [node for node in canonical_nodes if _is_risky_node(node)]
    pending_risky_nodes = [node for node in risky_nodes if _node_needs_manual_review(node)]
    resolved_risky_nodes = [node for node in risky_nodes if node.node_id not in {item.node_id for item in pending_risky_nodes}]

    return LegalKbRevisionDetailResponse(
        document=_serialize_document(bundle.document),
        revision=_serialize_revision(bundle.revision),
        source_asset=_serialize_source_asset(bundle.source_asset) if bundle.source_asset else None,
        canonical_nodes=canonical_nodes,
        metadata_proposals=metadata_proposals,
        relations=relations,
        summary=_serialize_summary(bundle.summary) if bundle.summary else None,
        retrieval_units=[
            _serialize_retrieval_unit(unit)
            for unit in sorted(
                bundle.revision.retrieval_units,
                key=lambda item: (
                    item.citation_label or "",
                    item.created_at.isoformat() if item.created_at else "",
                ),
            )
        ],
        review_events=[
            _serialize_review_event(event)
            for event in sorted(
                bundle.revision.review_events,
                key=lambda item: item.created_at.isoformat() if item.created_at else "",
            )
        ],
        publish_blockers=publish_blockers,
        pending_metadata=pending_metadata,
        pending_relations=pending_relations,
        pending_risky_nodes=pending_risky_nodes,
        resolved_risky_nodes=resolved_risky_nodes,
        resolved_risky_count=len(resolved_risky_nodes),
        risky_reference_only_count=sum(1 for node in risky_nodes if _is_reference_only_node(node)),
        risky_answerable_count=sum(1 for node in risky_nodes if _is_answerable_node(node)),
        is_ready_to_publish=len(publish_blockers) == 0,
    )


def _is_risky_node(node: LegalKbNodeOut) -> bool:
    return node.node_type in {"appendix", "form", "image_caption", "table"}


def _is_reference_only_node(node: LegalKbNodeOut) -> bool:
    return bool(node.structured_content.get("review_only")) or node.structured_content.get("answerable") is False


def _is_answerable_node(node: LegalKbNodeOut) -> bool:
    return node.structured_content.get("answerable") is True and not bool(node.structured_content.get("review_only"))


def _node_needs_usage_decision(node: LegalKbNodeOut) -> bool:
    if _is_reference_only_node(node):
        return False
    return _is_risky_node(node) and "answerable" not in node.structured_content


def _node_needs_manual_review(node: LegalKbNodeOut) -> bool:
    return _is_risky_node(node) and (node.review_status == "needs_review" or _node_needs_usage_decision(node))


def _model_node_needs_usage_decision(node) -> bool:
    structured_content = getattr(node, "structured_content", None) or {}
    if bool(structured_content.get("review_only")):
        return False
    return node.node_type in {"appendix", "form", "image_caption", "table"} and "answerable" not in structured_content


def _model_node_needs_manual_review(node) -> bool:
    return node.node_type in {"appendix", "form", "image_caption", "table"} and (
        node.review_status == "needs_review" or _model_node_needs_usage_decision(node)
    )


def _serialize_revision_list_item(
    *,
    revision: LegalKbRevision,
    source_file_name: str | None,
) -> LegalKbRevisionListItemOut:
    document = revision.document
    source_asset = revision.source_asset
    relations = sorted(
        [
            relation
            for relation in document.outgoing_relations + document.incoming_relations
            if relation.source_document_id == document.document_id or relation.target_document_id == document.document_id
        ],
        key=lambda relation: relation.created_at or revision.created_at or revision.uploaded_at,
    )
    summary = next(
        (
            item
            for item in revision.standard_summaries
            if item.revision_id == revision.revision_id
        ),
        None,
    )
    bundle = _ManagedDocumentBundle(
        document=document,
        revision=revision,
        source_asset=source_asset,
        relations=relations,
        summary=summary,
    )
    pending_metadata_count = sum(1 for proposal in revision.metadata_proposals if proposal.review_status != "approved")
    pending_relations_count = sum(
        1
        for relation in relations
        if relation.source_document_id == document.document_id
        and relation_review_status(relation) != "approved"
    )
    pending_risky_nodes_count = sum(1 for node in revision.canonical_nodes if _model_node_needs_manual_review(node))
    publish_blockers_count = len(collect_publish_blockers(bundle))
    latest_review_event_at = max(
        (
            event.created_at
            for event in revision.review_events
            if event.created_at is not None and getattr(event, "decision", None) != "created"
        ),
        default=None,
    )

    return LegalKbRevisionListItemOut(
        revision_id=revision.revision_id,
        document_id=revision.document_id,
        title=document.title,
        document_number=document.document_number,
        document_type=document.document_type,
        issuing_authority=document.issuing_authority,
        effective_date=document.effective_date,
        expiry_date=document.expiry_date,
        review_status=revision.review_status,
        publication_status=revision.publication_status,
        ingestion_status=revision.ingestion_status,
        legal_status=document.legal_status,
        source_file_name=source_file_name,
        pending_metadata_count=pending_metadata_count,
        pending_relations_count=pending_relations_count,
        pending_risky_nodes_count=pending_risky_nodes_count,
        summary_status=summary.review_status if summary else "missing",
        publish_blockers_count=publish_blockers_count,
        is_ready_to_publish=publish_blockers_count == 0,
        relation_count=len(relations),
        uploaded_at=revision.uploaded_at,
        updated_at=latest_review_event_at,
    )


def _serialize_document(document) -> LegalKbDocumentOut:
    return LegalKbDocumentOut(
        document_id=document.document_id,
        title=document.title,
        document_number=document.document_number,
        document_type=document.document_type,
        issuing_authority=document.issuing_authority,
        issued_date=document.issued_date,
        effective_date=document.effective_date,
        expiry_date=document.expiry_date,
        legal_status=document.legal_status,
        metadata_json=getattr(document, "metadata_json", None) or {},
    )


def _serialize_revision(revision) -> LegalKbRevisionOut:
    return LegalKbRevisionOut(
        revision_id=revision.revision_id,
        document_id=revision.document_id,
        revision_number=revision.revision_number,
        ingestion_status=revision.ingestion_status,
        review_status=revision.review_status,
        publication_status=revision.publication_status,
        checksum_sha256=revision.checksum_sha256,
        source_url=revision.source_url,
        source_downloaded_at=revision.source_downloaded_at,
        source_note=revision.source_note,
        parser_version=revision.parser_version,
        uploaded_at=revision.uploaded_at,
    )


def _serialize_source_asset(source_asset) -> LegalKbSourceAssetOut:
    return LegalKbSourceAssetOut(
        asset_id=source_asset.asset_id,
        document_id=source_asset.document_id,
        revision_id=source_asset.revision_id,
        asset_role=source_asset.asset_role,
        storage_uri=source_asset.storage_uri,
        original_filename=source_asset.original_filename,
        mime_type=source_asset.mime_type,
        sha256=source_asset.sha256,
        file_size_bytes=source_asset.file_size_bytes,
        source_url=source_asset.source_url,
        source_downloaded_at=source_asset.source_downloaded_at,
        source_note=source_asset.source_note,
    )


def _apply_revision_source_updates(
    revision: LegalKbRevision,
    source_asset: LegalKbSourceAsset | None,
    updates: dict,
) -> None:
    for field_name in ("source_url", "source_downloaded_at", "source_note"):
        if field_name in updates:
            setattr(revision, field_name, updates[field_name])
            if source_asset is not None:
                setattr(source_asset, field_name, updates[field_name])
    if source_asset is not None and "source_file_name" in updates:
        source_asset.original_filename = updates["source_file_name"]


def _source_media_type(file_name: str | None) -> str:
    media_type, _ = mimetypes.guess_type(file_name or "")
    return media_type or "application/octet-stream"


def _safe_local_source_path(storage_uri: str) -> Path | None:
    root = Path(settings.kb_local_storage_path).resolve()
    path = Path(storage_uri).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def _serve_source_asset(source_asset: LegalKbSourceAsset):
    media_type = _source_media_type(source_asset.original_filename)
    disposition = "inline" if media_type == "application/pdf" else "attachment"
    if is_object_uri(source_asset.storage_uri):
        url = get_object_storage().public_or_presigned_url(
            source_asset.storage_uri,
            content_disposition=f'{disposition}; filename="{source_asset.original_filename}"',
        )
        return RedirectResponse(
            url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Cache-Control": "private, max-age=300"},
        )

    source_path = _safe_local_source_path(source_asset.storage_uri)
    if source_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tệp nguồn của văn bản này.",
        )
    return FileResponse(
        source_path,
        media_type=media_type,
        filename=source_asset.original_filename or source_path.name,
        content_disposition_type=disposition,
        headers={"Cache-Control": "private, max-age=300"},
    )


def _serialize_node(node) -> LegalKbNodeOut:
    return LegalKbNodeOut(
        node_id=node.node_id,
        revision_id=node.revision_id,
        parent_id=node.parent_id,
        node_type=node.node_type,
        label=node.label,
        text=node.text,
        order_index=node.order_index,
        review_status=node.review_status,
        provenance=node.provenance,
        structured_content=node.structured_content,
    )


def _serialize_metadata_proposal(proposal: LegalKbMetadataProposal) -> LegalKbMetadataProposalOut:
    return LegalKbMetadataProposalOut(
        proposal_id=proposal.proposal_id,
        document_id=proposal.document_id,
        revision_id=proposal.revision_id,
        field_name=proposal.field_name,
        proposed_value=proposal.proposed_value,
        source_type=proposal.source_type,
        confidence=proposal.confidence,
        review_status=proposal.review_status,
        provenance=proposal.provenance,
        review_note=proposal.review_note,
        reviewed_by=proposal.reviewed_by,
        reviewed_at=proposal.reviewed_at,
        created_at=proposal.created_at,
    )


def _serialize_relation(relation: LegalKbRelation) -> LegalKbRelationOut:
    return LegalKbRelationOut(
        relation_id=relation.relation_id,
        source_document_id=relation.source_document_id,
        target_document_id=relation.target_document_id,
        relation_type=relation.relation_type,
        source_locator=relation.source_locator,
        target_locator=relation.target_locator,
        review_status=relation_review_status(relation),
        metadata_json=relation.metadata_json,
        created_at=relation.created_at,
    )


def _serialize_summary(summary: LegalKbSummary) -> LegalKbSummaryOut:
    return LegalKbSummaryOut(
        summary_id=summary.summary_id,
        document_id=summary.document_id,
        revision_id=summary.revision_id,
        content=summary.content,
        review_status=summary.review_status,
        approved_by=summary.approved_by,
        approved_at=summary.approved_at,
    )


def _serialize_retrieval_unit(unit) -> LegalKbRetrievalUnitOut:
    return LegalKbRetrievalUnitOut(
        retrieval_unit_id=unit.retrieval_unit_id,
        canonical_node_id=unit.canonical_node_id,
        document_id=unit.document_id,
        revision_id=unit.revision_id,
        answerable_status=unit.answerable_status,
        citation_label=unit.citation_label,
        embedding_model=unit.embedding_model,
        embedding_version=unit.embedding_version,
        index_version=unit.index_version,
    )


def _serialize_review_event(event) -> LegalKbReviewEventOut:
    return LegalKbReviewEventOut(
        review_event_id=event.review_event_id,
        document_id=event.document_id,
        revision_id=event.revision_id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        decision=event.decision,
        actor_user_id=event.actor_user_id,
        details=event.details,
        created_at=event.created_at,
    )


def _parse_iso_date(value: str, *, field_name: str):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be YYYY-MM-DD",
        ) from exc


def _parse_optional_iso_date(value: str | None, *, field_name: str):
    if value in {None, ""}:
        return None
    return _parse_iso_date(value, field_name=field_name)


@dataclass
class _ManagedDocumentBundle:
    document: LegalKbDocument
    revision: LegalKbRevision
    source_asset: LegalKbSourceAsset | None
    relations: list[LegalKbRelation]
    summary: LegalKbSummary | None


def _managed_bundle_from_document(document: LegalKbDocument) -> _ManagedDocumentBundle | None:
    managed_revisions = [
        revision
        for revision in document.revisions
        if revision.publication_status in {"published", "suspended", "archived"}
    ]
    if not managed_revisions:
        return None
    revision = max(
        managed_revisions,
        key=lambda item: item.created_at or item.uploaded_at,
    )
    source_asset = revision.source_asset or next(
        (
            asset
            for asset in document.source_assets
            if asset.revision_id == revision.revision_id and asset.asset_role == "source"
        ),
        None,
    )
    relations = sorted(
        [
            relation
            for relation in document.outgoing_relations + document.incoming_relations
            if relation.source_document_id == document.document_id or relation.target_document_id == document.document_id
        ],
        key=lambda relation: relation.created_at or revision.created_at,
    )
    summary = next(
        (
            item
            for item in revision.standard_summaries
            if item.revision_id == revision.revision_id
        ),
        None,
    )
    return _ManagedDocumentBundle(
        document=document,
        revision=revision,
        source_asset=source_asset,
        relations=relations,
        summary=summary,
    )


def _current_repository_revision(document: LegalKbDocument) -> LegalKbRevision | None:
    managed_revisions = [
        revision
        for revision in document.revisions
        if revision.publication_status in {"published", "suspended", "archived"}
    ]
    if not managed_revisions:
        return None
    return max(
        managed_revisions,
        key=lambda item: item.created_at or item.uploaded_at,
    )


async def _load_managed_document_bundle(session: AsyncSession, document_id: str):
    stmt = (
        select(LegalKbDocument)
        .where(LegalKbDocument.document_id == document_id)
        .options(
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.source_asset),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.source_assets),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.canonical_nodes),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.metadata_proposals),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.standard_summaries),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.retrieval_units),
            selectinload(LegalKbDocument.revisions).selectinload(LegalKbRevision.review_events),
            selectinload(LegalKbDocument.source_assets),
            selectinload(LegalKbDocument.outgoing_relations),
            selectinload(LegalKbDocument.incoming_relations),
        )
    )
    document = await session.scalar(stmt)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy văn bản trong kho.")
    bundle = _managed_bundle_from_document(document)
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Văn bản này chưa có bản công bố để quản lý trong kho.",
        )
    return bundle


def _document_matches_query(document: LegalKbDocument, normalized_query: str) -> bool:
    values = [
        document.title or "",
        document.document_number or "",
        document.document_type or "",
        document.issuing_authority or "",
    ]
    return any(normalized_query in value.lower() for value in values)


def _display_status_for_bundle(bundle) -> str:
    lifecycle_label = str((bundle.document.metadata_json or {}).get("lifecycle_label") or "").strip().lower()
    if bundle.revision.publication_status == "suspended" or bundle.document.legal_status == "suspended":
        return "suspended"
    if lifecycle_label in {"replaced", "annulled"}:
        return lifecycle_label
    if bundle.document.legal_status == "expired":
        return "expired"
    return "active"


def _refresh_retrieval_units(bundle) -> None:
    for retrieval_unit in bundle.revision.retrieval_units:
        retrieval_unit.effective_from = bundle.document.effective_date
        retrieval_unit.effective_to = bundle.document.expiry_date
        answerable = bool((retrieval_unit.metadata_json or {}).get("answerable", True))
        retrieval_unit.answerable_status = _document_answerable_status(bundle.document) if answerable else "not_answerable"


def _document_answerable_status(document: LegalKbDocument) -> str:
    today = date.today()
    if document.legal_status == "suspended":
        return "suspended"
    if document.effective_date and document.effective_date > today:
        return "future"
    if document.expiry_date and document.expiry_date <= today:
        return "historical"
    if document.legal_status == "expired":
        return "historical"
    return "active"
