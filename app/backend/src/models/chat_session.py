"""Persisted chat sessions and messages owned by authenticated users."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from src.models.base import Base


class ChatSession(Base):
    __tablename__ = "qa_sessions"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_qa_sessions_session_user"),
        Index("idx_qa_sessions_user_updated", "user_id", "updated_at"),
        Index("idx_qa_sessions_user_created", "user_id", "created_at"),
    )

    session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    is_bookmarked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    bookmark_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bookmarked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        primaryjoin=lambda: (ChatSession.session_id == foreign(ChatMessage.session_id))
        & (ChatSession.user_id == foreign(ChatMessage.user_id)),
    )


class ChatMessage(Base):
    __tablename__ = "qa_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["qa_sessions.session_id", "qa_sessions.user_id"],
            name="fk_qa_messages_session_user",
            ondelete="CASCADE",
        ),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_qa_messages_role"),
        Index("idx_qa_messages_session_created", "session_id", "created_at"),
        Index("idx_qa_messages_user_created", "user_id", "created_at"),
    )

    message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default="[]")
    response_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_out_of_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ChatSession] = relationship(
        back_populates="messages",
        primaryjoin=lambda: (ChatSession.session_id == foreign(ChatMessage.session_id))
        & (ChatSession.user_id == foreign(ChatMessage.user_id)),
    )
