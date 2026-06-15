"""HITL review endpoints for extracted QCVN assets."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.schemas import AssetReviewItemOut, AssetReviewRequest
from src.auth.dependencies import require_admin
from src.db.session import get_session
from src.models.document_asset import DocumentAsset
from src.models.user import User

router = APIRouter(prefix="/admin", tags=["admin-assets"], dependencies=[Depends(require_admin)])
_PUBLISH_STATUSES = {"pending", "approved", "rejected", "private"}
_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _out(asset: DocumentAsset) -> AssetReviewItemOut:
    return AssetReviewItemOut(
        asset_id=asset.asset_id,
        doc_id=asset.doc_id,
        asset_kind=asset.asset_kind,
        source_locator=asset.source_locator,
        relationship_id=asset.relationship_id,
        caption=asset.caption,
        alt_text=asset.alt_text,
        mapping_confidence=asset.mapping_confidence,
        publish_status=asset.publish_status,
        checksum=asset.checksum,
    )


@router.get("/traffic-sign-assets/review", response_model=list[AssetReviewItemOut])
async def list_assets_for_review(
    publish_status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    db_session: AsyncSession = Depends(get_session),
):
    assets = (
        await db_session.scalars(
            select(DocumentAsset)
            .where(
                DocumentAsset.asset_kind.in_(("sign_image", "sign_group")),
                DocumentAsset.publish_status == publish_status,
            )
            .order_by(DocumentAsset.created_at.asc())
            .limit(limit)
        )
    ).all()
    return [_out(asset) for asset in assets]


@router.patch("/traffic-sign-assets/{asset_id}", response_model=AssetReviewItemOut)
async def review_traffic_sign_asset(
    asset_id: str,
    payload: AssetReviewRequest,
    current_user: User = Depends(require_admin),
    db_session: AsyncSession = Depends(get_session),
):
    if payload.publish_status not in _PUBLISH_STATUSES:
        raise HTTPException(status_code=422, detail="Trạng thái phát hành không hợp lệ.")
    if payload.mapping_confidence not in _CONFIDENCE_LEVELS:
        raise HTTPException(status_code=422, detail="Mức tin cậy ánh xạ không hợp lệ.")
    if payload.publish_status == "approved" and payload.mapping_confidence == "low":
        raise HTTPException(
            status_code=409,
            detail="Không thể phát hành tài nguyên có mức tin cậy thấp.",
        )
    asset = await db_session.get(DocumentAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên.")
    asset.publish_status = payload.publish_status
    asset.mapping_confidence = payload.mapping_confidence
    asset.caption = payload.caption
    asset.alt_text = payload.alt_text
    asset.reviewed_by = current_user.user_id
    asset.reviewed_at = datetime.now(tz=UTC)
    await db_session.commit()
    await db_session.refresh(asset)
    return _out(asset)
