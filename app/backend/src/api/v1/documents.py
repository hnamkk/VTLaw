import mimetypes
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse
from langchain_openai import ChatOpenAI
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas import (
    DocumentsResponse,
    LegalDocumentOut,
    LegalKbDocumentSummaryOut,
    LegalKbDynamicSummaryRequest,
    LegalKbHistoricalCitationOut,
    LegalKbPublicDocumentDetailOut,
    PublicDocumentRelationOut,
)
from src.core.config import settings
from src.db.session import get_session
from src.legal_kb.review import relation_review_status
from src.legal_kb.summaries import build_dynamic_summary, get_standard_summary
from src.models.legal_kb import (
    LegalKbDocument,
    LegalKbRelation,
    LegalKbRetrievalUnit,
    LegalKbRevision,
    LegalKbSourceAsset,
)
from src.storage.object_storage import get_object_storage, is_object_uri

router = APIRouter(tags=["documents"])

_KB_VIEWER_WARNING = (
    "Bản này phục vụ tra cứu trong hệ thống. Khi sử dụng cho mục đích pháp lý hoặc chính thức, "
    "vui lòng đối chiếu với nguồn văn bản chính thức."
)
_KB_VIEWER_WARNING_HEADER = (
    "Ban nay phuc vu tra cuu trong he thong. Khi su dung cho muc dich phap ly hoac chinh thuc, "
    "vui long doi chieu voi nguon van ban chinh thuc."
)
_PUBLIC_SOURCE_NOT_FOUND_DETAIL = "Không tìm thấy file nguồn đã công bố."
_PUBLIC_DOCUMENT_NOT_FOUND_DETAIL = "Không tìm thấy văn bản."
_HISTORICAL_CITATION_NOT_FOUND_DETAIL = "Không tìm thấy trích dẫn lịch sử."
_PUBLIC_DOCUMENT_FALLBACK_TITLE = "Văn bản đã công bố"
_PUBLIC_UNKNOWN_ISSUER = "Chưa cập nhật"


def _ensure_legal_kb_public_enabled() -> None:
    """Compat shim after KB cutover: public document routes are always available."""
    return None


def _safe_legal_kb_source_path(source_path: str | None) -> Path | None:
    if not source_path:
        return None
    root = Path(settings.kb_local_storage_path).resolve()
    path = Path(source_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def _source_media_type(file_name: str | None) -> str:
    media_type, _ = mimetypes.guess_type(file_name or "")
    return media_type or "application/octet-stream"


def _latest_published_revision_subquery():
    return (
        select(
            LegalKbRevision.document_id.label("document_id"),
            func.max(LegalKbRevision.revision_number).label("revision_number"),
        )
        .where(LegalKbRevision.publication_status == "published")
        .group_by(LegalKbRevision.document_id)
        .subquery()
    )


async def _get_legal_kb_public_document(
    db_session: AsyncSession,
    document_id: str,
):
    latest_published = _latest_published_revision_subquery()
    result = await db_session.execute(
        select(LegalKbDocument, LegalKbRevision, LegalKbSourceAsset)
        .join(
            latest_published,
            latest_published.c.document_id == LegalKbDocument.document_id,
        )
        .join(
            LegalKbRevision,
            and_(
                LegalKbRevision.document_id == latest_published.c.document_id,
                LegalKbRevision.revision_number == latest_published.c.revision_number,
            ),
        )
        .outerjoin(LegalKbSourceAsset, LegalKbSourceAsset.asset_id == LegalKbRevision.source_asset_id)
        .where(
            LegalKbDocument.document_id == document_id,
            LegalKbDocument.legal_status == "active",
        )
        .limit(1)
    )
    return result.one_or_none()


async def _get_legal_kb_historical_citation(
    db_session: AsyncSession,
    retrieval_unit_id: str,
):
    result = await db_session.execute(
        select(LegalKbRetrievalUnit, LegalKbDocument, LegalKbRevision, LegalKbSourceAsset)
        .join(LegalKbDocument, LegalKbDocument.document_id == LegalKbRetrievalUnit.document_id)
        .join(LegalKbRevision, LegalKbRevision.revision_id == LegalKbRetrievalUnit.revision_id)
        .outerjoin(LegalKbSourceAsset, LegalKbSourceAsset.asset_id == LegalKbRevision.source_asset_id)
        .where(
            LegalKbRetrievalUnit.retrieval_unit_id == retrieval_unit_id,
            LegalKbRevision.publication_status.in_(("published", "suspended", "archived")),
        )
        .limit(1)
    )
    return result.one_or_none()


def _serve_legal_kb_source(asset: LegalKbSourceAsset):
    media_type = _source_media_type(asset.original_filename)
    disposition = "inline" if media_type == "application/pdf" else "attachment"
    headers = {
        "Cache-Control": "private, max-age=300",
        "X-LegalAI-Viewer-Warning": _KB_VIEWER_WARNING_HEADER,
    }
    if is_object_uri(asset.storage_uri):
        url = get_object_storage().public_or_presigned_url(
            asset.storage_uri,
            content_disposition=f'{disposition}; filename="{asset.original_filename}"',
        )
        return RedirectResponse(
            url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers=headers,
        )

    source_path = _safe_legal_kb_source_path(asset.storage_uri)
    if source_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_SOURCE_NOT_FOUND_DETAIL)

    return FileResponse(
        source_path,
        media_type=media_type,
        filename=asset.original_filename or source_path.name,
        content_disposition_type=disposition,
        headers=headers,
    )


def _serialize_legal_kb_public_item(
    *,
    document: LegalKbDocument,
    revision: LegalKbRevision,
    source_asset: LegalKbSourceAsset | None,
    relations: list[PublicDocumentRelationOut] | None = None,
) -> LegalDocumentOut:
    return LegalDocumentOut(
        doc_id=document.document_id,
        title=document.title or _PUBLIC_DOCUMENT_FALLBACK_TITLE,
        document_number=getattr(document, "document_number", None),
        doc_type=document.document_type or "UNKNOWN",
        status=document.legal_status,
        issued_date=getattr(document, "issued_date", None),
        effective_date=document.effective_date or date.today(),
        expiry_date=document.expiry_date,
        issuer=document.issuing_authority or _PUBLIC_UNKNOWN_ISSUER,
        source_url=revision.source_url or (source_asset.source_url if source_asset else None),
        source_file_name=source_asset.original_filename if source_asset else None,
        source_download_url=(
            f"/api/v1/documents/{document.document_id}/source" if source_asset else None
        ),
        viewer_warning=_KB_VIEWER_WARNING,
        standard_summary_url=f"/api/v1/documents/{document.document_id}/summary",
        current_revision_id=revision.revision_id,
        relations=relations or [],
    )


def _serialize_public_relation(
    relation: LegalKbRelation,
    *,
    document_id: str,
) -> PublicDocumentRelationOut:
    is_outgoing = relation.source_document_id == document_id
    counterpart = relation.target_document if is_outgoing else relation.source_document
    return PublicDocumentRelationOut(
        relation_id=relation.relation_id,
        relation_type=relation.relation_type,
        direction="outgoing" if is_outgoing else "incoming",
        source_locator=relation.source_locator,
        target_locator=relation.target_locator,
        counterpart_document_id=counterpart.document_id,
        counterpart_title=counterpart.title,
        counterpart_document_number=counterpart.document_number,
        counterpart_legal_status=counterpart.legal_status,
    )


async def _public_relations_by_document(
    db_session: AsyncSession,
    document_ids: list[str],
) -> dict[str, list[PublicDocumentRelationOut]]:
    if not document_ids:
        return {}

    rows = (
        await db_session.execute(
            select(LegalKbRelation)
            .options(
                selectinload(LegalKbRelation.source_document),
                selectinload(LegalKbRelation.target_document),
            )
            .where(
                or_(
                    LegalKbRelation.source_document_id.in_(document_ids),
                    LegalKbRelation.target_document_id.in_(document_ids),
                )
            )
        )
    ).scalars().unique().all()

    relations: dict[str, list[PublicDocumentRelationOut]] = {document_id: [] for document_id in document_ids}
    for relation in rows:
        if relation_review_status(relation) != "approved":
            continue
        if relation.source_document_id in relations:
            relations[relation.source_document_id].append(
                _serialize_public_relation(relation, document_id=relation.source_document_id)
            )
        if relation.target_document_id in relations:
            relations[relation.target_document_id].append(
                _serialize_public_relation(relation, document_id=relation.target_document_id)
            )

    for items in relations.values():
        items.sort(key=lambda item: (item.counterpart_document_number or "", item.relation_type))
    return relations


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(
    q: Optional[str] = Query(None, description="Search query by document title"),
    doc_type: Optional[str] = Query(
        None, description="Document type filter (e.g., LUAT, NGHI_DINH)"
    ),
    issuer: Optional[str] = Query(None, description="Partial match for issuer"),
    year: Optional[int] = Query(None, description="Year of the effective date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db_session: AsyncSession = Depends(get_session),
):
    """GET /api/v1/documents."""
    _ensure_legal_kb_public_enabled()
    latest_published = _latest_published_revision_subquery()
    query = (
        select(LegalKbDocument, LegalKbRevision, LegalKbSourceAsset)
        .join(
            latest_published,
            latest_published.c.document_id == LegalKbDocument.document_id,
        )
        .join(
            LegalKbRevision,
            and_(
                LegalKbRevision.document_id == latest_published.c.document_id,
                LegalKbRevision.revision_number == latest_published.c.revision_number,
            ),
        )
        .outerjoin(LegalKbSourceAsset, LegalKbSourceAsset.asset_id == LegalKbRevision.source_asset_id)
        .where(LegalKbDocument.legal_status == "active")
    )

    if q:
        keyword = q.strip()
        query = query.where(
            or_(
                LegalKbDocument.title.ilike(f"%{keyword}%"),
                LegalKbDocument.document_number.ilike(f"%{keyword}%"),
            )
        )
    if doc_type:
        query = query.where(LegalKbDocument.document_type == doc_type.strip())
    if issuer:
        query = query.where(LegalKbDocument.issuing_authority.ilike(f"%{issuer.strip()}%"))
    if year:
        query = query.where(extract("year", LegalKbDocument.effective_date) == year)

    count_result = await db_session.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    rows = (
        await db_session.execute(
            query.order_by(
                LegalKbDocument.effective_date.desc().nullslast(),
                LegalKbDocument.title.asc().nullslast(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    relation_map = await _public_relations_by_document(
        db_session,
        [document.document_id for document, _revision, _source_asset in rows],
    )

    return DocumentsResponse(
        items=[
            _serialize_legal_kb_public_item(
                document=document,
                revision=revision,
                source_asset=source_asset,
                relations=relation_map.get(document.document_id, []),
            )
            for document, revision, source_asset in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=LegalKbPublicDocumentDetailOut)
async def get_legal_kb_public_document_detail(
    document_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_public_enabled()
    row = await _get_legal_kb_public_document(db_session, document_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_DOCUMENT_NOT_FOUND_DETAIL)

    document, revision, source_asset = row
    return LegalKbPublicDocumentDetailOut(
        document_id=document.document_id,
        revision_id=revision.revision_id,
        title=document.title,
        document_number=document.document_number,
        document_type=document.document_type,
        issuing_authority=document.issuing_authority,
        effective_date=document.effective_date,
        expiry_date=document.expiry_date,
        legal_status=document.legal_status,
        publication_status=revision.publication_status,
        source_file_name=source_asset.original_filename if source_asset else None,
        source_download_url=(
            f"/api/v1/documents/{document.document_id}/source" if source_asset else None
        ),
        standard_summary_url=f"/api/v1/documents/{document.document_id}/summary",
        viewer_warning=_KB_VIEWER_WARNING,
    )


@router.get("/documents/{doc_id}/source")
async def view_document_source(
    doc_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    """Serve the approved source file without exposing its storage path."""
    _ensure_legal_kb_public_enabled()
    row = await _get_legal_kb_public_document(db_session, doc_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_SOURCE_NOT_FOUND_DETAIL)
    _, _, source_asset = row
    if source_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_SOURCE_NOT_FOUND_DETAIL)
    return _serve_legal_kb_source(source_asset)


@router.get("/documents/citations/{retrieval_unit_id}", response_model=LegalKbHistoricalCitationOut)
async def get_legal_kb_historical_citation(
    retrieval_unit_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_public_enabled()
    row = await _get_legal_kb_historical_citation(db_session, retrieval_unit_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_HISTORICAL_CITATION_NOT_FOUND_DETAIL)

    retrieval_unit, document, revision, source_asset = row
    return LegalKbHistoricalCitationOut(
        retrieval_unit_id=retrieval_unit.retrieval_unit_id,
        document_id=document.document_id,
        revision_id=revision.revision_id,
        title=document.title,
        document_number=document.document_number,
        citation_label=retrieval_unit.citation_label,
        legal_status=document.legal_status,
        publication_status=revision.publication_status,
        source_file_name=source_asset.original_filename if source_asset else None,
        source_download_url=(
            f"/api/v1/documents/citations/{retrieval_unit.retrieval_unit_id}/source"
            if source_asset
            else None
        ),
        viewer_warning=_KB_VIEWER_WARNING,
        historical=True,
    )


@router.get("/documents/citations/{retrieval_unit_id}/source")
async def view_legal_kb_historical_citation_source(
    retrieval_unit_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_public_enabled()
    row = await _get_legal_kb_historical_citation(db_session, retrieval_unit_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_HISTORICAL_CITATION_NOT_FOUND_DETAIL)
    _, _, _, source_asset = row
    if source_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_SOURCE_NOT_FOUND_DETAIL)
    return _serve_legal_kb_source(source_asset)


@router.get("/documents/{document_id}/summary", response_model=LegalKbDocumentSummaryOut)
async def get_legal_kb_document_summary(
    document_id: str,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_public_enabled()
    if await _get_legal_kb_public_document(db_session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_DOCUMENT_NOT_FOUND_DETAIL)
    summary = await get_standard_summary(db_session, document_id=document_id)
    return LegalKbDocumentSummaryOut(
        document_id=summary.document_id,
        revision_id=summary.revision_id,
        summary_type="standard",
        content=summary.content,
    )


@router.post("/documents/{document_id}/summary/dynamic", response_model=LegalKbDocumentSummaryOut)
async def create_legal_kb_dynamic_summary(
    document_id: str,
    request: LegalKbDynamicSummaryRequest,
    db_session: AsyncSession = Depends(get_session),
):
    _ensure_legal_kb_public_enabled()
    if await _get_legal_kb_public_document(db_session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PUBLIC_DOCUMENT_NOT_FOUND_DETAIL)
    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        openai_api_key=settings.OPENAI_API_KEY,
        streaming=False,
        temperature=0.0,
    )
    result = await build_dynamic_summary(
        db_session,
        document_id=document_id,
        prompt=request.prompt,
        query_date=request.query_date or date.today(),
        llm=llm,
    )
    return LegalKbDocumentSummaryOut(
        document_id=document_id,
        revision_id="dynamic",
        summary_type="dynamic",
        content=result.content,
        effective_date=request.query_date or date.today(),
        citations=[citation.model_dump(mode="json") for citation in result.citations],
        faithfulness_score=result.faithfulness_score,
        related_document_ids=list(result.related_document_ids),
    )
