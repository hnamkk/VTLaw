"""Repealed-document replacement lookup (spec 11 §4, spec 12 §7).

Given a doc_id flagged as repealed, find the active document that replaces it
via the legal_documents.replaced_by_id chain.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.legal_document import LegalDocument


async def find_replacement(
    session: AsyncSession,
    doc_id: str,
    max_depth: int = 5,
) -> LegalDocument | None:
    """Walk the replaced_by chain until an active document is found.

    Returns None if the chain ends without an active document or exceeds max_depth.
    """
    visited: set[str] = set()
    current_id: str | None = doc_id
    depth = 0

    while current_id and depth < max_depth and current_id not in visited:
        visited.add(current_id)
        depth += 1

        stmt = select(LegalDocument).where(LegalDocument.doc_id == current_id)
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if doc is None:
            return None

        if doc.status == "active":
            return doc

        current_id = doc.replaced_by_id

    return None
