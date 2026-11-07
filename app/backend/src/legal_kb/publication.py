from __future__ import annotations

from copy import copy
from datetime import date
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, inspect, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import NO_VALUE

from src.core.config import settings
from src.legal_kb.metadata import normalize_document_role
from src.legal_kb.retrieval_units import (
    RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION,
    build_retrieval_units,
    citation_mismatches_for_nodes,
    node_is_answerable,
)
from src.legal_kb.review import (
    apply_approved_metadata_to_document,
    apply_approved_metadata_values,
    load_revision_bundle,
    normalize_legacy_revision_review_state,
    relation_review_status,
)
from src.models.legal_kb import LegalKbRetrievalUnit, LegalKbReviewEvent, LegalKbRevision

REQUIRED_METADATA_FIELDS = (
    "title",
    "document_type",
    "issuing_authority",
    "issued_date",
    "effective_date",
    "document_role",
)
AMENDMENT_RELATION_TYPES = {"amends", "supplements", "replaces", "annuls"}
NO_ANSWERABLE_NODE_BLOCKER = (
    "Chưa có mục nội dung đã duyệt nào được dùng cho hỏi đáp. "
    "Hãy đánh dấu ít nhất một mục là dùng cho hỏi đáp trước khi đưa vào kho."
)
CITATION_MISMATCH_BLOCKER = (
    "Một số mục nội dung có trích dẫn chưa khớp Điều/Khoản/Điểm. "
    "Hãy chạy lại chuẩn hóa trích dẫn trước khi đưa vào kho."
)
ORPHAN_LOCATOR_BLOCKER = (
    "Một số Khoản/Điểm chưa gắn đúng Điều/Khoản cha. "
    "Hãy rebuild cấu trúc văn bản trước khi đưa vào kho."
)


async def publish_revision(
    session: AsyncSession,
    *,
    revision_id: str,
    actor_user_id: str | None,
) -> tuple[object, list[str]]:
    bundle = await load_revision_bundle(session, revision_id, for_update=True)
    normalize_legacy_revision_review_state(bundle)
    if bundle.revision.publication_status == "published":
        blockers = collect_publish_blockers(bundle)
        if blockers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "KB_PUBLISH_BLOCKED", "blockers": blockers},
            )
        if bundle.revision.review_status != "approved":
            bundle.revision.review_status = "approved"
            session.add(
                LegalKbReviewEvent(
                    review_event_id=_uuid(),
                    document_id=bundle.document.document_id,
                    revision_id=bundle.revision.revision_id,
                    entity_type="revision",
                    entity_id=bundle.revision.revision_id,
                    decision="updated",
                    actor_user_id=actor_user_id,
                    details={"action": "normalize_published_review_status"},
                )
            )
            await session.commit()
        return bundle.revision, []

    blockers = collect_publish_blockers(bundle)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "KB_PUBLISH_BLOCKED", "blockers": blockers},
        )
    projected_document = copy(bundle.document)
    apply_approved_metadata_values(projected_document, bundle.revision.metadata_proposals)
    generated = await build_retrieval_units(document=projected_document, revision=bundle.revision)
    if generated.answerable_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "KB_PUBLISH_BLOCKED",
                "blockers": [NO_ANSWERABLE_NODE_BLOCKER],
            },
        )

    try:
        apply_approved_metadata_to_document(bundle)

        await session.execute(
            delete(LegalKbRetrievalUnit).where(LegalKbRetrievalUnit.revision_id == bundle.revision.revision_id)
        )
        for retrieval_unit in generated.units:
            session.add(retrieval_unit)

        await _archive_previous_repository_revisions(session, bundle)
        bundle.revision.publication_status = "published"
        bundle.revision.review_status = "approved"
        bundle.document.legal_status = _published_legal_status(bundle.document)
        session.add(
            LegalKbReviewEvent(
                review_event_id=_uuid(),
                document_id=bundle.document.document_id,
                revision_id=bundle.revision.revision_id,
                entity_type="revision",
                entity_id=bundle.revision.revision_id,
                decision="published",
                actor_user_id=actor_user_id,
                details={
                    "retrieval_units": len(generated.units),
                    "answerable_units": generated.answerable_count,
                },
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return bundle.revision, blockers


async def _archive_previous_repository_revisions(session: AsyncSession, bundle) -> None:
    await session.execute(
        update(LegalKbRevision)
        .where(
            LegalKbRevision.document_id == bundle.document.document_id,
            LegalKbRevision.revision_id != bundle.revision.revision_id,
            LegalKbRevision.publication_status.in_(("published", "suspended")),
        )
        .values(publication_status="archived")
    )
    await session.execute(
        update(LegalKbRetrievalUnit)
        .where(
            LegalKbRetrievalUnit.document_id == bundle.document.document_id,
            LegalKbRetrievalUnit.revision_id != bundle.revision.revision_id,
        )
        .values(answerable_status="historical")
    )
    loaded_revisions = inspect(bundle.document).attrs.revisions.loaded_value
    if loaded_revisions is NO_VALUE:
        return
    for revision in loaded_revisions:
        if (
            revision.revision_id != bundle.revision.revision_id
            and revision.publication_status in {"published", "suspended"}
        ):
            revision.publication_status = "archived"
            loaded_units = inspect(revision).attrs.retrieval_units.loaded_value
            if loaded_units is NO_VALUE:
                continue
            for retrieval_unit in loaded_units:
                retrieval_unit.answerable_status = "historical"


async def suspend_revision(
    session: AsyncSession,
    *,
    revision_id: str,
    actor_user_id: str | None,
    reason: str,
) -> object:
    bundle = await load_revision_bundle(session, revision_id)
    bundle.revision.publication_status = "suspended"
    bundle.document.legal_status = "suspended"
    for retrieval_unit in bundle.revision.retrieval_units:
        retrieval_unit.answerable_status = "suspended"

    session.add(
        LegalKbReviewEvent(
            review_event_id=_uuid(),
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="revision",
            entity_id=bundle.revision.revision_id,
            decision="suspended",
            actor_user_id=actor_user_id,
            details={"reason": reason.strip()},
        )
    )
    await session.commit()
    return bundle.revision


async def unsuspend_revision(
    session: AsyncSession,
    *,
    revision_id: str,
    actor_user_id: str | None,
) -> object:
    bundle = await load_revision_bundle(session, revision_id)
    normalize_legacy_revision_review_state(bundle)
    blockers = collect_publish_blockers(bundle)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "KB_PUBLISH_BLOCKED", "blockers": blockers},
        )
    if bundle.revision.publication_status != "suspended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "KB_NOT_SUSPENDED", "blockers": []},
        )

    bundle.revision.publication_status = "published"
    bundle.revision.review_status = "approved"
    bundle.document.legal_status = _published_legal_status(bundle.document)
    for retrieval_unit in bundle.revision.retrieval_units:
        answerable = bool((retrieval_unit.metadata_json or {}).get("answerable", True))
        retrieval_unit.answerable_status = (
            _restored_answerable_status(document=bundle.document) if answerable else "not_answerable"
        )

    session.add(
        LegalKbReviewEvent(
            review_event_id=_uuid(),
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="revision",
            entity_id=bundle.revision.revision_id,
            decision="published",
            actor_user_id=actor_user_id,
            details={"restored_from": "suspended"},
        )
    )
    await session.commit()
    return bundle.revision


def collect_publish_blockers(bundle) -> list[str]:
    blockers: list[str] = []
    if bundle.source_asset is None or not bundle.source_asset.sha256:
        blockers.append("Missing source asset checksum.")
    if settings.KB_REQUIRE_OBJECT_STORAGE and bundle.source_asset is not None:
        if bundle.source_asset.metadata_json.get("storage_backend") != "object":
            blockers.append("Object storage is required for kho văn bản source assets.")
    if bundle.revision.ingestion_status != "parsed":
        blockers.append("Revision parsing is incomplete or failed.")

    approved_by_field = _approved_metadata_by_field(bundle.revision.metadata_proposals)
    for field_name in REQUIRED_METADATA_FIELDS:
        if not approved_by_field.get(field_name):
            blockers.append(f"Required metadata field is not approved: {field_name}.")

    for field_name, values in _active_metadata_values(bundle.revision.metadata_proposals).items():
        if len(values) > 1:
            blockers.append(f"Metadata conflict is unresolved: {field_name}.")

    unreviewed_nodes = [node for node in bundle.revision.canonical_nodes if node.review_status == "needs_review"]
    if unreviewed_nodes:
        blockers.append("Canonical nodes still need admin review.")

    orphan_locator_nodes = [
        node
        for node in bundle.revision.canonical_nodes
        if node.review_status == "approved"
        and node.node_type in {"clause", "point"}
        and node.parent_id is None
    ]
    if orphan_locator_nodes:
        blockers.append(ORPHAN_LOCATOR_BLOCKER)

    risky_nodes_without_decision = [
        node
        for node in bundle.revision.canonical_nodes
        if node.review_status == "approved"
        and node.node_type in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION
        and not bool((node.structured_content or {}).get("review_only"))
        and "answerable" not in (node.structured_content or {})
    ]
    if risky_nodes_without_decision:
        blockers.append("Approved table/form/appendix/image nodes need answerable or review-only decision.")

    answerable_nodes = [
        node
        for node in bundle.revision.canonical_nodes
        if node.review_status == "approved" and node_is_answerable(node)
    ]
    if not answerable_nodes:
        blockers.append(NO_ANSWERABLE_NODE_BLOCKER)

    citation_mismatches = citation_mismatches_for_nodes(list(bundle.revision.canonical_nodes))
    if citation_mismatches:
        blockers.append(CITATION_MISMATCH_BLOCKER)
        blockers.extend(citation_mismatches[:10])

    if bundle.summary is None:
        blockers.append("Summary proposal is missing.")
    elif bundle.summary.review_status != "approved":
        blockers.append("Summary proposal is not approved.")

    document_role = normalize_document_role(
        approved_by_field.get("document_role") or bundle.document.metadata_json.get("document_role")
    )
    if document_role == "amendment":
        approved_relations = [
            relation
            for relation in bundle.relations
            if relation.source_document_id == bundle.document.document_id
            and relation.relation_type in AMENDMENT_RELATION_TYPES
            and relation_review_status(relation) == "approved"
        ]
        if not approved_relations:
            blockers.append("Amendment relation is unresolved.")
    return blockers


def _approved_metadata_by_field(proposals) -> dict[str, str]:
    approved: dict[str, str] = {}
    for proposal in proposals:
        if proposal.review_status == "approved":
            approved[proposal.field_name] = proposal.proposed_value
    return approved


def _active_metadata_values(proposals) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for proposal in proposals:
        if proposal.review_status == "rejected":
            continue
        values.setdefault(proposal.field_name, set()).add(proposal.proposed_value)
    return values


def _published_legal_status(document) -> str:
    today = date.today()
    if document.effective_date and document.effective_date > today:
        return "future_effective"
    if document.expiry_date and document.expiry_date < today:
        return "expired"
    return "active"


def _restored_answerable_status(*, document) -> str:
    today = date.today()
    if document.effective_date and document.effective_date > today:
        return "future"
    if document.expiry_date and document.expiry_date < today:
        return "historical"
    if document.legal_status == "suspended":
        return "suspended"
    return "active"


def _uuid() -> str:
    return str(uuid4())
