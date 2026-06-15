"""Consistent document and chunk lifecycle transitions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.document_lifecycle_event import DocumentLifecycleEvent
from src.models.legal_document import LegalDocument

_LEGAL_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def current_legal_date() -> date:
    return datetime.now(tz=_LEGAL_TIMEZONE).date()


def document_expiry_on(document: LegalDocument) -> date | None:
    """Return the first date on which the document is no longer searchable."""
    return document.valid_to or document.expiry_date


def is_document_expired(document: LegalDocument, *, as_of: date) -> bool:
    expiry_on = document_expiry_on(document)
    return bool(
        document.review_status == "approved"
        and expiry_on is not None
        and expiry_on <= as_of
    )


def sync_document_chunks(document: LegalDocument) -> None:
    """Mirror the root lifecycle fields used by retrieval onto every chunk."""
    valid_to = document_expiry_on(document)
    for chunk in document.chunks:
        chunk.status = document.status
        chunk.effective_date = document.effective_date
        chunk.valid_from = document.valid_from or document.effective_date
        chunk.valid_to = valid_to
        chunk.rag_enabled = document.rag_enabled and document.status == "active"
        chunk.provision_status = (
            "repealed"
            if document.status == "repealed"
            else "future_effective"
            if document.legal_status == "future_effective"
            else "active"
        )


def apply_expired_state(document: LegalDocument, *, expiry_on: date) -> None:
    document.expiry_date = expiry_on
    document.valid_to = expiry_on
    document.status = "repealed"
    document.legal_status = "repealed"
    document.rag_scope = "disabled"
    document.rag_enabled = False
    sync_document_chunks(document)


def apply_current_state(document: LegalDocument, *, as_of: date) -> None:
    """Resolve future, active, or expired state from approved lifecycle metadata."""
    if document.status == "repealed" or document.legal_status == "repealed":
        document.status = "repealed"
        document.legal_status = "repealed"
        document.rag_scope = "disabled"
        document.rag_enabled = False
        sync_document_chunks(document)
        return
    if is_document_expired(document, as_of=as_of):
        apply_expired_state(document, expiry_on=document_expiry_on(document) or as_of)
        return
    if document.valid_from and document.valid_from > as_of:
        document.status = "pending_review"
        document.legal_status = "future_effective"
        document.rag_enabled = False
    else:
        document.status = "active"
        document.legal_status = "active"
        document.rag_enabled = document.rag_scope != "disabled"
    sync_document_chunks(document)


async def count_expiry_candidates(db_session: AsyncSession, *, as_of: date) -> int:
    expiry = func.coalesce(LegalDocument.valid_to, LegalDocument.expiry_date)
    return int(
        await db_session.scalar(
            select(func.count())
            .select_from(LegalDocument)
            .where(
                LegalDocument.review_status == "approved",
                LegalDocument.status != "repealed",
                expiry.is_not(None),
                expiry <= as_of,
            )
        )
        or 0
    )


async def reconcile_expired_documents(
    db_session: AsyncSession,
    *,
    as_of: date,
    source: str = "scheduler",
) -> list[str]:
    """Archive approved expired documents atomically; safe to run repeatedly."""
    expiry = func.coalesce(LegalDocument.valid_to, LegalDocument.expiry_date)
    documents = list(
        (
            await db_session.scalars(
                select(LegalDocument)
                .where(
                    LegalDocument.review_status == "approved",
                    LegalDocument.status != "repealed",
                    expiry.is_not(None),
                    expiry <= as_of,
                )
                .options(selectinload(LegalDocument.chunks))
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    changed: list[str] = []
    for document in documents:
        expiry_on = document_expiry_on(document)
        if expiry_on is None:
            continue
        previous_status = document.status
        previous_legal_status = document.legal_status
        apply_expired_state(document, expiry_on=expiry_on)
        db_session.add(
            DocumentLifecycleEvent(
                doc_id=document.doc_id,
                event_type="expired",
                source=source,
                effective_on=expiry_on,
                previous_status=previous_status,
                previous_legal_status=previous_legal_status,
                new_status=document.status,
                new_legal_status=document.legal_status,
                details={"as_of": as_of.isoformat()},
            )
        )
        changed.append(document.doc_id)
    return changed
