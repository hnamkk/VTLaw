"""Helpers for creating and broadcasting user notifications."""

from __future__ import annotations

from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument
from src.models.notification import InAppNotification
from src.notifications.broker import notification_broker


def _change_type_label(change_type: str) -> str:
    return {
        "create": "Văn bản mới",
        "update": "Cập nhật văn bản",
        "repeal": "Bãi bỏ/thay thế văn bản",
    }.get(change_type, "Cập nhật văn bản")


def _notification_summary(document: LegalDocument, queue: KbUpdateQueue) -> str:
    label = _change_type_label(queue.change_type).lower()
    issuer = document.issuer or "Cơ quan ban hành"
    if queue.change_type == "repeal" and document.expiry_date:
        return f"{label} từ {issuer}, hết hiệu lực từ {document.expiry_date:%d/%m/%Y}."
    return f"{label} từ {issuer}, có hiệu lực từ {document.effective_date:%d/%m/%Y}."


async def create_approval_notification(
    db_session,
    *,
    document: LegalDocument,
    queue: KbUpdateQueue,
) -> InAppNotification:
    notification = InAppNotification(
        doc_id=document.doc_id,
        queue_id=queue.queue_id,
        change_type=queue.change_type,
        title=document.title,
        summary=_notification_summary(document, queue),
    )
    db_session.add(notification)
    await db_session.flush()
    return notification


async def publish_notification(notification: InAppNotification) -> None:
    await notification_broker.publish(
        {
            "type": "notification",
            "notification": {
                "notification_id": notification.notification_id,
                "doc_id": notification.doc_id,
                "queue_id": notification.queue_id,
                "change_type": notification.change_type,
                "title": notification.title,
                "summary": notification.summary,
                "is_read": False,
                "created_at": notification.created_at.isoformat(),
            },
        }
    )
