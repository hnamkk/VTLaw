"""In-app notifications generated from approved KB changes."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class InAppNotification(Base):
    __tablename__ = "in_app_notifications"
    __table_args__ = (
        Index("idx_notifications_created_at", "created_at"),
        Index("idx_notifications_doc_created", "doc_id", "created_at"),
    )

    notification_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    queue_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("kb_update_queue.queue_id", ondelete="SET NULL"),
        nullable=True,
    )
    change_type: Mapped[str] = mapped_column(String(12), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserNotificationRead(Base):
    __tablename__ = "user_notification_reads"
    __table_args__ = (
        UniqueConstraint("user_id", "notification_id", name="uq_user_notification_read"),
        Index("idx_notif_reads_user", "user_id"),
    )

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    notification_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("in_app_notifications.notification_id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
