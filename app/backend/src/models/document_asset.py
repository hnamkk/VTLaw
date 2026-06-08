"""Metadata for immutable source and derived document assets."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.legal_document import LegalDocument
    from src.models.traffic_sign import TrafficSign


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    asset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()")
    )
    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(180), nullable=True)
    relationship_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    display_format: Mapped[str | None] = mapped_column(String(20), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_asset_key: Mapped[str] = mapped_column(String(500), nullable=False)
    display_asset_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_asset_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publish_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    duplicate_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_confidence: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'low'")
    )
    reviewed_by: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["LegalDocument"] = relationship(back_populates="assets")
    primary_for_signs: Mapped[list["TrafficSign"]] = relationship(
        back_populates="primary_asset", foreign_keys="TrafficSign.primary_asset_id"
    )

    __table_args__ = (
        CheckConstraint(
            "asset_kind IN ('source', 'pdf_rendition', 'sign_image', "
            "'sign_group', 'figure', 'table_image')",
            name="chk_document_asset_kind",
        ),
        CheckConstraint(
            "publish_status IN ('pending', 'approved', 'rejected', 'private')",
            name="chk_document_asset_publish_status",
        ),
        CheckConstraint(
            "mapping_confidence IN ('high', 'medium', 'low')",
            name="chk_document_asset_mapping_confidence",
        ),
        UniqueConstraint("doc_id", "checksum", "asset_kind", name="uq_document_asset_checksum"),
    )
