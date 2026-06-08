"""Reviewed traffic-sign catalog backed by official QCVN assets."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.document_asset import DocumentAsset
    from src.models.document_chunk import DocumentChunk


class TrafficSign(Base):
    __tablename__ = "traffic_signs"

    sign_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sign_code: Mapped[str] = mapped_column(String(40), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    sign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    sign_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
    meaning_text: Mapped[str] = mapped_column(Text, nullable=False)
    recognition_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("document_chunks.chunk_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_section_path: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    primary_asset_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("document_assets.asset_id", ondelete="SET NULL"),
        nullable=True,
    )
    related_asset_ids: Mapped[list[str]] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=False, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, server_default=text("'active'")
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source_chunk: Mapped["DocumentChunk"] = relationship()
    primary_asset: Mapped["DocumentAsset | None"] = relationship(
        back_populates="primary_for_signs", foreign_keys=[primary_asset_id]
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'repealed', 'pending_review')",
            name="chk_traffic_sign_status",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="chk_traffic_sign_review_status",
        ),
    )
