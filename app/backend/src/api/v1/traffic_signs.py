"""Public traffic-sign catalog and reviewed asset delivery."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas import (
    TrafficSignAssetOut,
    TrafficSignListResponse,
    TrafficSignOut,
)
from src.core.config import settings
from src.db.session import get_session
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.traffic_sign import TrafficSign
from src.storage.object_storage import get_object_storage, is_object_uri, make_object_uri

router = APIRouter(tags=["traffic-signs"])
_ASSET_ROOT = (Path(__file__).resolve().parents[3] / "storage" / "assets").resolve()


def normalize_sign_code(value: str) -> str:
    compact = re.sub(r"[\s-]+", ".", value.strip().upper())
    compact = re.sub(r"\.{2,}", ".", compact)
    if "." not in compact and re.fullmatch(r"[PWRIS]\d{2,3}[A-Z]?", compact):
        compact = f"{compact[0]}.{compact[1:]}"
    return compact.lower()


def normalize_sign_query(value: str) -> str:
    cleaned = re.sub(
        r"\b(?:trông như thế nào|cho xem|nhận biết|hình gì|màu gì|là biển nào)\b",
        " ",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" ?.,")


def _asset_out(asset: DocumentAsset | None) -> TrafficSignAssetOut | None:
    if asset is None or asset.publish_status != "approved":
        return None
    return TrafficSignAssetOut(
        asset_id=asset.asset_id,
        url=f"/api/v1/assets/{asset.asset_id}",
        width=asset.width,
        height=asset.height,
        mime_type=asset.mime_type,
    )


def _sign_out(sign: TrafficSign) -> TrafficSignOut:
    return TrafficSignOut(
        sign_code=sign.sign_code,
        sign_name=sign.sign_name,
        aliases=list(sign.aliases or []),
        sign_group=sign.sign_group,
        recognition_text=sign.recognition_text,
        meaning_text=sign.meaning_text,
        application_text=sign.application_text,
        exception_text=sign.exception_text,
        source_locator=" → ".join(sign.source_section_path),
        citation_chunk_id=sign.source_chunk_id,
        primary_asset=_asset_out(sign.primary_asset),
    )


def _public_filters(today: date) -> tuple:
    return (
        TrafficSign.status == "active",
        TrafficSign.review_status == "approved",
        or_(TrafficSign.valid_from.is_(None), TrafficSign.valid_from <= today),
        or_(TrafficSign.valid_to.is_(None), TrafficSign.valid_to > today),
        DocumentChunk.status == "active",
        DocumentChunk.rag_enabled.is_(True),
    )


@router.get("/traffic-signs", response_model=TrafficSignListResponse)
async def list_traffic_signs(
    query: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(3, ge=1, le=20),
    db_session: AsyncSession = Depends(get_session),
):
    search_query = normalize_sign_query(query)
    normalized = normalize_sign_code(search_query)
    pattern = f"%{search_query}%"
    stmt = (
        select(TrafficSign)
        .join(DocumentChunk, DocumentChunk.chunk_id == TrafficSign.source_chunk_id)
        .options(selectinload(TrafficSign.primary_asset))
        .where(*_public_filters(date.today()))
        .where(
            or_(
                TrafficSign.normalized_code == normalized,
                TrafficSign.sign_name.ilike(pattern),
                TrafficSign.recognition_text.ilike(pattern),
                TrafficSign.aliases.any(search_query),
            )
        )
        .order_by(
            (TrafficSign.normalized_code == normalized).desc(),
            TrafficSign.sign_code.asc(),
        )
        .limit(limit)
    )
    signs = list((await db_session.scalars(stmt)).all())
    return TrafficSignListResponse(items=[_sign_out(sign) for sign in signs], total=len(signs))


@router.get("/traffic-signs/{sign_code}", response_model=TrafficSignOut)
async def get_traffic_sign(
    sign_code: str,
    db_session: AsyncSession = Depends(get_session),
):
    sign = await db_session.scalar(
        select(TrafficSign)
        .join(DocumentChunk, DocumentChunk.chunk_id == TrafficSign.source_chunk_id)
        .options(selectinload(TrafficSign.primary_asset))
        .where(*_public_filters(date.today()))
        .where(TrafficSign.normalized_code == normalize_sign_code(sign_code))
    )
    if sign is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy biển báo đã được xác minh.")
    return _sign_out(sign)


@router.get("/assets/{asset_id}")
async def get_public_asset(
    asset_id: str,
    request: Request,
    variant: str = Query("display", pattern="^(display|thumbnail|original)$"),
    db_session: AsyncSession = Depends(get_session),
):
    asset = await db_session.get(DocumentAsset, asset_id)
    if asset is None or asset.publish_status != "approved":
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên đã được duyệt.")
    asset_key = {
        "display": asset.display_asset_key,
        "thumbnail": asset.thumbnail_asset_key,
        "original": asset.original_asset_key,
    }[variant] or asset.original_asset_key
    path = (_ASSET_ROOT / asset_key).resolve()
    if (not path.is_relative_to(_ASSET_ROOT) or not path.is_file()) and settings.OBJECT_STORAGE_ENABLED:
        uri = asset_key if is_object_uri(asset_key) else make_object_uri(settings.S3_BUCKET, asset_key)
        etag = f'"{asset.checksum}-{variant}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        url = get_object_storage().public_or_presigned_url(uri)
        return RedirectResponse(
            url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=300",
                "X-Content-Type-Options": "nosniff",
            },
        )
    if not path.is_relative_to(_ASSET_ROOT) or not path.is_file():
        raise HTTPException(status_code=404, detail="Tệp tài nguyên không khả dụng.")
    etag = f'"{asset.checksum}-{variant}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return FileResponse(
        path,
        media_type=asset.mime_type,
        content_disposition_type="inline",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
