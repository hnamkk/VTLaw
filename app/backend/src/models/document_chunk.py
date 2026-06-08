"""Document chunk model (hierarchical legal text + embedding)."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.models.base import Base

if TYPE_CHECKING:
    from src.models.legal_document import LegalDocument


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    doc_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("legal_documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    chapter_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    article_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clause_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    point_num: Mapped[str | None] = mapped_column(String(10), nullable=True)
    canonical_provision_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    locator_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    locator_label: Mapped[str | None] = mapped_column(String(180), nullable=True)
    section_path: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    section_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sign_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    figure_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default=text("'{}'")
    )
    table_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asset_ids: Mapped[list[str]] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=False, server_default=text("'{}'")
    )
    corpus: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'road_law'")
    )
    rag_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    provision_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'active'")
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Denormalized from legal_documents for fast active filtering.
    status: Mapped[str] = mapped_column(String(15), nullable=False, server_default=text("'active'"))
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(settings.EMBEDDING_DIM), nullable=True
    )
    # Generated column (TSVECTOR) — READ-ONLY. Postgres tự tính từ text_content qua
    # Computed(); SQLAlchemy không emit cột này trong INSERT/UPDATE thông thường, và mọi
    # nỗ lực ghi tường minh đều bị DB từ chối. KHÔNG gán giá trị cho thuộc tính này.
    text_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', text_content)", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped["LegalDocument"] = relationship(back_populates="chunks")

    __table_args__ = (
        CheckConstraint(
            "chunk_type IN ('chuong', 'dieu', 'khoan', 'diem', 'phu_luc', "
            "'technical_section', 'definition', 'sign_group', 'sign_definition', "
            "'installation_rule', 'table', 'figure_caption', 'appendix_item')",
            name="chk_chunk_type",
        ),
        CheckConstraint(
            "(chunk_type = 'chuong' AND chapter_num IS NOT NULL) OR "
            "(chunk_type IN ('dieu', 'khoan', 'diem') AND article_num IS NOT NULL) OR "
            "(chunk_type IN ('phu_luc', 'technical_section', 'definition', 'sign_group', "
            "'sign_definition', 'installation_rule', 'table', 'figure_caption', "
            "'appendix_item'))",
            name="chk_chunk_hierarchy",
        ),
        CheckConstraint(
            "provision_status IN ('future_effective', 'active', 'repealed')",
            name="chk_chunk_provision_status",
        ),
    )
