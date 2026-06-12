"""Hierarchical chunking for Vietnamese legal documents (spec 10).

Public surface: ``chunk_document`` plus the ``ChunkDraft``/``DocMeta`` types.
"""

from __future__ import annotations

from src.rag.chunking.base import (
    CHUNK_TYPE_CHUONG,
    CHUNK_TYPE_DIEM,
    CHUNK_TYPE_DIEU,
    CHUNK_TYPE_FIGURE_CAPTION,
    CHUNK_TYPE_KHOAN,
    CHUNK_TYPE_PHU_LUC,
    CHUNK_TYPE_SIGN_DEFINITION,
    CHUNK_TYPE_SIGN_GROUP,
    CHUNK_TYPE_TABLE,
    CHUNK_TYPE_TECHNICAL_SECTION,
    ChunkDraft,
    DocMeta,
)
from src.rag.chunking.chunker import build_embedding_content, chunk_document

__all__ = [
    "ChunkDraft",
    "DocMeta",
    "chunk_document",
    "build_embedding_content",
    "CHUNK_TYPE_CHUONG",
    "CHUNK_TYPE_DIEU",
    "CHUNK_TYPE_KHOAN",
    "CHUNK_TYPE_DIEM",
    "CHUNK_TYPE_PHU_LUC",
    "CHUNK_TYPE_TECHNICAL_SECTION",
    "CHUNK_TYPE_SIGN_DEFINITION",
    "CHUNK_TYPE_SIGN_GROUP",
    "CHUNK_TYPE_TABLE",
    "CHUNK_TYPE_FIGURE_CAPTION",
]
