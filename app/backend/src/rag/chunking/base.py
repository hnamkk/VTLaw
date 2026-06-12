"""Types for the hierarchical chunker (spec 10 §4–§5).

``ChunkDraft`` is the chunker's output: an in-memory chunk that the ingestion
service later embeds and persists as a ``document_chunks`` row. ``status`` and
``effective_date`` are NOT on the draft — they are denormalized from the parent
``legal_documents`` row at persist time, keeping the chunker pure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# chunk_type values allowed by the DB check constraint (see document_chunk model).
CHUNK_TYPE_CHUONG = "chuong"
CHUNK_TYPE_DIEU = "dieu"
CHUNK_TYPE_KHOAN = "khoan"
CHUNK_TYPE_DIEM = "diem"
CHUNK_TYPE_PHU_LUC = "phu_luc"
CHUNK_TYPE_TECHNICAL_SECTION = "technical_section"
CHUNK_TYPE_SIGN_DEFINITION = "sign_definition"
CHUNK_TYPE_SIGN_GROUP = "sign_group"
CHUNK_TYPE_TABLE = "table"
CHUNK_TYPE_FIGURE_CAPTION = "figure_caption"


@dataclass
class DocMeta:
    """Document-level metadata used to enrich ``embedding_content`` (spec 10 §5)."""

    title: str
    doc_type: str
    effective_date: str  # ISO date string, rendered into the embedding header
    status: str
    document_number: str | None = None
    corpus: str = "road_law"
    parser_profile: str = "legal"
    parser_version: str = "legal-v2"


@dataclass
class ChunkDraft:
    """One chunk before embedding/persistence.

    Maps onto ``document_chunks`` columns; ``embedding_content`` is transient
    (used only to compute the vector, never stored verbatim).
    """

    text_content: str
    chunk_type: str
    embedding_content: str = ""
    chapter_num: int | None = None
    article_num: int | None = None
    clause_num: int | None = None
    point_num: str | None = None
    # Goes into metadata_json.
    display_path: str = ""
    heading_path: list[str] = field(default_factory=list)
    source_page: int | None = None
    source_order: int | None = None
    content_kind: str = "legal_text"
    canonical_provision_id: str | None = None
    locator_type: str | None = None
    locator_label: str | None = None
    section_path: list[str] = field(default_factory=list)
    section_number: str | None = None
    sign_codes: list[str] = field(default_factory=list)
    figure_ids: list[str] = field(default_factory=list)
    table_id: str | None = None

    def metadata_json(self, parser_confidence: float) -> dict:
        return {
            "display_path": self.display_path,
            "heading_path": self.heading_path,
            "source_page": self.source_page,
            "source_order": self.source_order,
            "content_kind": self.content_kind,
            "canonical_provision_id": self.canonical_provision_id,
            "locator_type": self.locator_type,
            "locator_label": self.locator_label,
            "section_path": self.section_path,
            "section_number": self.section_number,
            "sign_codes": self.sign_codes,
            "figure_ids": self.figure_ids,
            "table_id": self.table_id,
            "parser_confidence": parser_confidence,
        }
