import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.schemas import (
    NotificationListResponse,
    NotificationOut,
    NotificationUnreadCountResponse,
)
from src.auth.dependencies import require_user
from src.db.session import get_session
from src.models.notification import InAppNotification, UserNotificationRead
from src.models.user import User
from src.notifications.broker import notification_broker

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_payload(notification: InAppNotification, *, is_read: bool) -> NotificationOut:
    return NotificationOut(
        notification_id=notification.notification_id,
        doc_id=notification.doc_id,
        queue_id=notification.queue_id,
        change_type=notification.change_type,
        title=notification.title,
        summary=notification.summary,
        is_read=is_read,
        created_at=notification.created_at,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    read_exists = (
        select(UserNotificationRead.notification_id)
        .where(
            UserNotificationRead.user_id == current_user.user_id,
            UserNotificationRead.notification_id == InAppNotification.notification_id,
        )
        .exists()
    )

    base_query = select(InAppNotification, read_exists.label("is_read"))
    if unread_only:
        base_query = base_query.where(~read_exists)

    total = await db_session.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    result = await db_session.execute(
        base_query.order_by(desc(InAppNotification.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return NotificationListResponse(
        items=[
            _notification_payload(notification, is_read=bool(is_read))
            for notification, is_read in result.all()
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def get_unread_notification_count(
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    read_exists = exists().where(
        UserNotificationRead.user_id == current_user.user_id,
        UserNotificationRead.notification_id == InAppNotification.notification_id,
    )
    count = await db_session.scalar(
        select(func.count()).select_from(InAppNotification).where(~read_exists)
    )
    return NotificationUnreadCountResponse(unread_count=count or 0)


@router.patch("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: str,
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    notification = await db_session.scalar(
        select(InAppNotification.notification_id).where(
            InAppNotification.notification_id == notification_id
        )
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    await db_session.execute(
        pg_insert(UserNotificationRead)
        .values(user_id=current_user.user_id, notification_id=notification_id)
        .on_conflict_do_nothing(index_elements=["user_id", "notification_id"])
    )
    await db_session.commit()


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    db_session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
):
    result = await db_session.execute(select(InAppNotification.notification_id))
    rows = [
        {"user_id": current_user.user_id, "notification_id": notification_id}
        for notification_id in result.scalars().all()
    ]
    if rows:
        await db_session.execute(
            pg_insert(UserNotificationRead)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["user_id", "notification_id"])
        )
        await db_session.commit()


@router.get("/stream")
async def stream_notifications(
    request: Request,
    current_user: User = Depends(require_user),
):
    async def event_generator():
        async for queue in notification_broker.subscribe():
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                    if await request.is_disconnected():
                        break
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        break
                    yield "event: ping\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
