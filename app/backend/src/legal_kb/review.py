from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.legal_kb.metadata import normalize_document_role, normalize_document_type
from src.models.legal_kb import (
    LegalKbNode,
    LegalKbRelation,
    LegalKbRevision,
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbReviewEvent,
    LegalKbSourceAsset,
    LegalKbSummary,
)

RELATION_TYPES = {"amends", "supplements", "replaces", "annuls", "guides", "depends_on"}
REVIEW_DECISIONS = {"approved", "rejected"}
RISKY_NODE_TYPES_REQUIRING_MANUAL_REVIEW = {"appendix", "form", "image_caption", "table"}
BULK_RISKY_NODE_REVIEW_MODES = {"answerable", "review_only", "reset", "rejected"}
ADMIN_REVIEW_ONLY_ROLE = "admin_review_only"


@dataclass
class LegalKbRevisionBundle:
    document: LegalKbDocument
    revision: LegalKbRevision
    source_asset: LegalKbSourceAsset | None
    summary: LegalKbSummary | None
    relations: list[LegalKbRelation]


async def load_revision_bundle(
    session: AsyncSession,
    revision_id: str,
    *,
    for_update: bool = False,
) -> LegalKbRevisionBundle:
    stmt = (
        select(LegalKbRevision)
        .where(LegalKbRevision.revision_id == revision_id)
        .options(
            selectinload(LegalKbRevision.document).selectinload(
                LegalKbDocument.outgoing_relations
            ),
            selectinload(LegalKbRevision.document).selectinload(
                LegalKbDocument.incoming_relations
            ),
            selectinload(LegalKbRevision.source_asset),
            selectinload(LegalKbRevision.source_assets),
            selectinload(LegalKbRevision.canonical_nodes),
            selectinload(LegalKbRevision.metadata_proposals),
            selectinload(LegalKbRevision.standard_summaries),
            selectinload(LegalKbRevision.retrieval_units),
            selectinload(LegalKbRevision.review_events),
        )
    )
    if for_update:
        stmt = stmt.with_for_update(of=LegalKbRevision)
    revision = await session.scalar(stmt)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản revision not found")

    document = revision.document
    source_asset = revision.source_asset or next(
        (asset for asset in revision.source_assets if asset.asset_role == "source"),
        None,
    )
    relations = sorted(
        [
            relation
            for relation in document.outgoing_relations + document.incoming_relations
            if relation.source_document_id == document.document_id
            or relation.target_document_id == document.document_id
        ],
        key=lambda relation: relation.created_at or datetime.min.replace(tzinfo=UTC),
    )
    summary = revision.standard_summaries[0] if revision.standard_summaries else None
    return LegalKbRevisionBundle(
        document=document,
        revision=revision,
        source_asset=source_asset,
        summary=summary,
        relations=relations,
    )


def normalize_legacy_revision_review_state(bundle: LegalKbRevisionBundle) -> bool:
    changed = False

    for proposal in bundle.revision.metadata_proposals:
        if proposal.source_type == "upload" and proposal.review_status == "needs_review":
            proposal.review_status = "approved"
            if not _should_defer_metadata_apply(bundle):
                _apply_approved_metadata(bundle.document, proposal.field_name, proposal.proposed_value)
            changed = True

    for node in bundle.revision.canonical_nodes:
        structured_content = node.structured_content or {}
        should_auto_approve = (
            node.review_status == "needs_review"
            and (
                node.node_type not in RISKY_NODE_TYPES_REQUIRING_MANUAL_REVIEW
                or bool(structured_content.get("review_only"))
            )
        )
        if should_auto_approve:
            node.review_status = "approved"
            changed = True

    return changed


async def create_metadata_proposal(
    session: AsyncSession,
    *,
    revision_id: str,
    field_name: str,
    proposed_value: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> LegalKbMetadataProposal:
    bundle = await load_revision_bundle(session, revision_id)
    proposal = LegalKbMetadataProposal(
        proposal_id=str(uuid4()),
        document_id=bundle.document.document_id,
        revision_id=bundle.revision.revision_id,
        field_name=field_name.strip(),
        proposed_value=proposed_value.strip(),
        source_type="admin",
        confidence=1.0,
        review_status="needs_review",
        provenance={"created_by": "admin"},
        review_note=note.strip() if note else None,
    )
    bundle.revision.review_status = "in_review"
    session.add(proposal)
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="document",
            entity_id=bundle.document.document_id,
            decision="updated",
            actor_user_id=actor_user_id,
            details={"field_name": proposal.field_name, "proposal_id": proposal.proposal_id},
        )
    )
    await session.commit()
    return proposal


async def review_metadata_proposal(
    session: AsyncSession,
    *,
    proposal_id: str,
    decision: str,
    actor_user_id: str | None,
    note: str | None = None,
    proposed_value: str | None = None,
) -> LegalKbMetadataProposal:
    proposal = await session.get(LegalKbMetadataProposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản metadata proposal not found"
        )
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid decision")

    bundle = await load_revision_bundle(session, proposal.revision_id)
    if proposed_value is not None:
        proposal.proposed_value = proposed_value.strip()
    proposal.review_status = decision
    proposal.review_note = note.strip() if note else None
    proposal.reviewed_by = actor_user_id
    proposal.reviewed_at = datetime.now(tz=UTC)
    if decision == "approved":
        if not _should_defer_metadata_apply(bundle):
            _apply_approved_metadata(bundle.document, proposal.field_name, proposal.proposed_value)
        for sibling in bundle.revision.metadata_proposals:
            if sibling.proposal_id != proposal.proposal_id and sibling.field_name == proposal.field_name:
                if sibling.review_status == "approved":
                    sibling.review_status = "rejected"
                if sibling.proposed_value != proposal.proposed_value and sibling.review_status == "needs_review":
                    sibling.review_status = "rejected"
    bundle.revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="document",
            entity_id=bundle.document.document_id,
            decision=decision,
            actor_user_id=actor_user_id,
            details={"field_name": proposal.field_name, "proposal_id": proposal.proposal_id},
        )
    )
    await session.commit()
    return proposal


async def review_canonical_node(
    session: AsyncSession,
    *,
    node_id: str,
    decision: str,
    actor_user_id: str | None,
    note: str | None = None,
    answerable: bool | None = None,
) -> LegalKbNode:
    node = await session.get(LegalKbNode, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản canonical node not found")
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid decision")

    bundle = await load_revision_bundle(session, node.revision_id)
    _apply_node_review_outcome(
        node,
        review_status=decision,
        note=note,
        answerable=answerable,
        review_only=(decision == "approved" and answerable is False),
    )
    bundle.revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="node",
            entity_id=node.node_id,
            decision=decision,
            actor_user_id=actor_user_id,
            details={"node_type": node.node_type},
        )
    )
    await session.commit()
    return node


async def reset_canonical_node_review(
    session: AsyncSession,
    *,
    node_id: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> LegalKbNode:
    node = await session.get(LegalKbNode, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản canonical node not found")

    bundle = await load_revision_bundle(session, node.revision_id)
    previous_review_status = node.review_status
    previous_structured_content = dict(node.structured_content or {})
    _apply_node_review_outcome(node, review_status="needs_review", note=note, reset_decision=True)
    bundle.revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="node",
            entity_id=node.node_id,
            decision="updated",
            actor_user_id=actor_user_id,
            details={
                "action": "reset_review",
                "node_type": node.node_type,
                "previous_review_status": previous_review_status,
                "previous_answerable": previous_structured_content.get("answerable"),
                "previous_review_only": previous_structured_content.get("review_only"),
            },
        )
    )
    await session.commit()
    return node


async def bulk_review_risky_nodes(
    session: AsyncSession,
    *,
    revision_id: str,
    node_type: str,
    mode: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> LegalKbRevisionBundle:
    if node_type not in RISKY_NODE_TYPES_REQUIRING_MANUAL_REVIEW:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid node_type")
    if mode not in BULK_RISKY_NODE_REVIEW_MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid mode")

    bundle = await load_revision_bundle(session, revision_id)
    target_nodes = [
        node
        for node in bundle.revision.canonical_nodes
        if node.node_type == node_type and not _is_parser_review_only(node)
    ]

    for node in target_nodes:
        previous_review_status = node.review_status
        previous_structured_content = dict(node.structured_content or {})
        if mode == "answerable":
            _apply_node_review_outcome(node, review_status="approved", note=note, answerable=True)
        elif mode == "review_only":
            _apply_node_review_outcome(node, review_status="approved", note=note, answerable=False, review_only=True)
        elif mode == "rejected":
            _apply_node_review_outcome(node, review_status="rejected", note=note)
        else:
            _apply_node_review_outcome(node, review_status="needs_review", note=note, reset_decision=True)

        session.add(
            _review_event(
                document_id=bundle.document.document_id,
                revision_id=bundle.revision.revision_id,
                entity_type="node",
                entity_id=node.node_id,
                decision="updated" if mode == "reset" else node.review_status,
                actor_user_id=actor_user_id,
                details={
                    "action": f"bulk_{mode}",
                    "node_type": node.node_type,
                    "previous_review_status": previous_review_status,
                    "previous_answerable": previous_structured_content.get("answerable"),
                    "previous_review_only": previous_structured_content.get("review_only"),
                },
            )
        )

    bundle.revision.review_status = "in_review"
    await session.commit()
    return bundle


async def create_relation_proposal(
    session: AsyncSession,
    *,
    revision_id: str,
    target_document_id: str,
    relation_type: str,
    actor_user_id: str | None,
    source_locator: str | None = None,
    target_locator: str | None = None,
    note: str | None = None,
) -> LegalKbRelation:
    if relation_type not in RELATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid relation_type"
        )

    bundle = await load_revision_bundle(session, revision_id)
    target_document = await session.get(LegalKbDocument, target_document_id)
    if target_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy văn bản liên quan.")
    if target_document_id == bundle.document.document_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Văn bản không thể tạo quan hệ với chính nó.",
        )
    duplicate = next(
        (
            relation
            for relation in bundle.document.outgoing_relations
            if relation.target_document_id == target_document_id
            and relation.relation_type == relation_type
        ),
        None,
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quan hệ này đã tồn tại.",
        )

    relation = LegalKbRelation(
        relation_id=str(uuid4()),
        source_document_id=bundle.document.document_id,
        target_document_id=target_document_id,
        relation_type=relation_type,
        source_locator=_strip_or_none(source_locator),
        target_locator=_strip_or_none(target_locator),
        metadata_json={
            "review_status": "needs_review",
            "source_type": "admin",
            "note": _strip_or_none(note),
            "created_by": actor_user_id,
        },
    )
    bundle.revision.review_status = "in_review"
    session.add(relation)
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="relation",
            entity_id=relation.relation_id,
            decision="created",
            actor_user_id=actor_user_id,
            details={"relation_type": relation_type, "target_document_id": target_document_id},
        )
    )
    await session.commit()
    return relation


async def review_relation(
    session: AsyncSession,
    *,
    relation_id: str,
    decision: str,
    actor_user_id: str | None,
    note: str | None = None,
) -> LegalKbRelation:
    relation = await session.get(LegalKbRelation, relation_id)
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản relation not found")
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid decision")

    revision = await session.scalar(
        select(LegalKbRevision)
        .where(LegalKbRevision.document_id == relation.source_document_id)
        .order_by(LegalKbRevision.created_at.desc())
    )
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản revision not found")

    metadata = dict(relation.metadata_json)
    metadata.update(
        {
            "review_status": decision,
            "reviewed_by": actor_user_id,
            "reviewed_at": datetime.now(tz=UTC).isoformat(),
            "review_note": _strip_or_none(note),
        }
    )
    relation.metadata_json = metadata
    revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=revision.document_id,
            revision_id=revision.revision_id,
            entity_type="relation",
            entity_id=relation.relation_id,
            decision=decision,
            actor_user_id=actor_user_id,
            details={"relation_type": relation.relation_type},
        )
    )
    await session.commit()
    return relation


async def update_relation_proposal(
    session: AsyncSession,
    *,
    relation_id: str,
    actor_user_id: str | None,
    target_document_id: str | None = None,
    relation_type: str | None = None,
    source_locator: str | None = None,
    target_locator: str | None = None,
    note: str | None = None,
) -> LegalKbRelation:
    relation = await session.get(LegalKbRelation, relation_id)
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản relation not found")
    if relation_type is not None and relation_type not in RELATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid relation_type"
        )
    if target_document_id is not None:
        target_document = await session.get(LegalKbDocument, target_document_id)
        if target_document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target document not found")
        if target_document_id == relation.source_document_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Relation target must be different from source document",
            )
        relation.target_document_id = target_document_id
    if relation_type is not None:
        relation.relation_type = relation_type
    relation.source_locator = _strip_or_none(source_locator)
    relation.target_locator = _strip_or_none(target_locator)

    revision = await session.scalar(
        select(LegalKbRevision)
        .where(LegalKbRevision.document_id == relation.source_document_id)
        .order_by(LegalKbRevision.created_at.desc())
    )
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản revision not found")

    metadata = dict(relation.metadata_json)
    metadata.update(
        {
            "review_status": "needs_review",
            "note": _strip_or_none(note),
            "updated_by": actor_user_id,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
    )
    metadata.pop("reviewed_by", None)
    metadata.pop("reviewed_at", None)
    metadata.pop("review_note", None)
    relation.metadata_json = metadata
    revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=revision.document_id,
            revision_id=revision.revision_id,
            entity_type="relation",
            entity_id=relation.relation_id,
            decision="updated",
            actor_user_id=actor_user_id,
            details={
                "relation_type": relation.relation_type,
                "target_document_id": relation.target_document_id,
            },
        )
    )
    await session.commit()
    return relation


async def delete_relation(
    session: AsyncSession,
    *,
    relation_id: str,
    actor_user_id: str | None,
) -> None:
    relation = await session.get(LegalKbRelation, relation_id)
    if relation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy quan hệ văn bản.")

    revision = await session.scalar(
        select(LegalKbRevision)
        .where(LegalKbRevision.document_id == relation.source_document_id)
        .order_by(LegalKbRevision.created_at.desc())
    )
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy hồ sơ nguồn của quan hệ.")

    if revision.publication_status == "draft":
        revision.review_status = "in_review"
    session.add(
        _review_event(
            document_id=revision.document_id,
            revision_id=revision.revision_id,
            entity_type="relation",
            entity_id=relation.relation_id,
            decision="deleted",
            actor_user_id=actor_user_id,
            details={
                "relation_type": relation.relation_type,
                "source_document_id": relation.source_document_id,
                "target_document_id": relation.target_document_id,
            },
        )
    )
    await session.delete(relation)
    await session.commit()


async def review_summary(
    session: AsyncSession,
    *,
    summary_id: str,
    decision: str,
    actor_user_id: str | None,
    content: str | None = None,
) -> LegalKbSummary:
    summary = await session.get(LegalKbSummary, summary_id)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kho văn bản summary not found")
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid decision")

    bundle = await load_revision_bundle(session, summary.revision_id)
    if content is not None:
        summary.content = content.strip()
    summary.review_status = decision
    if decision == "approved":
        summary.approved_by = actor_user_id
        summary.approved_at = datetime.now(tz=UTC)
    await _refresh_revision_status_after_summary_review(bundle)
    session.add(
        _review_event(
            document_id=bundle.document.document_id,
            revision_id=bundle.revision.revision_id,
            entity_type="summary",
            entity_id=summary.summary_id,
            decision=decision,
            actor_user_id=actor_user_id,
            details={"summary_id": summary.summary_id},
        )
    )
    await session.commit()
    return summary


async def _refresh_revision_status_after_summary_review(bundle: LegalKbRevisionBundle) -> None:
    if bundle.revision.publication_status != "published":
        bundle.revision.review_status = "in_review"
        return

    # Avoid leaving a published revision stuck in `in_review` when the only
    # action was approving the standard summary again.
    from src.legal_kb.publication import collect_publish_blockers

    blockers = collect_publish_blockers(bundle)
    bundle.revision.review_status = "approved" if not blockers else "in_review"


def relation_review_status(relation: LegalKbRelation) -> str:
    return str(relation.metadata_json.get("review_status") or "needs_review")


def _apply_approved_metadata(
    document: LegalKbDocument,
    field_name: str,
    proposed_value: str,
) -> None:
    if field_name in {"title", "document_number", "document_type", "issuing_authority"}:
        value = normalize_document_type(proposed_value) if field_name == "document_type" else proposed_value
        setattr(document, field_name, value)
        return
    if field_name in {"issued_date", "effective_date", "expiry_date"}:
        setattr(document, field_name, datetime.fromisoformat(proposed_value).date())
        return
    value = normalize_document_role(proposed_value) if field_name == "document_role" else proposed_value
    document.metadata_json = {**document.metadata_json, field_name: value}


def apply_approved_metadata_to_document(bundle: LegalKbRevisionBundle) -> None:
    apply_approved_metadata_values(bundle.document, bundle.revision.metadata_proposals)


def apply_approved_metadata_values(
    document: LegalKbDocument,
    proposals,
) -> None:
    for proposal in proposals:
        if proposal.review_status == "approved":
            _apply_approved_metadata(document, proposal.field_name, proposal.proposed_value)


def _should_defer_metadata_apply(bundle: LegalKbRevisionBundle) -> bool:
    return bundle.revision.publication_status == "draft" and bundle.revision.revision_number > 1


def _review_event(
    *,
    document_id: str,
    revision_id: str | None,
    entity_type: str,
    entity_id: str,
    decision: str,
    actor_user_id: str | None,
    details: dict,
) -> LegalKbReviewEvent:
    return LegalKbReviewEvent(
        review_event_id=str(uuid4()),
        document_id=document_id,
        revision_id=revision_id,
        entity_type=entity_type,
        entity_id=entity_id,
        decision=decision,
        actor_user_id=actor_user_id,
        details=details,
    )


def _apply_node_review_outcome(
    node: LegalKbNode,
    *,
    review_status: str,
    note: str | None = None,
    answerable: bool | None = None,
    review_only: bool | None = None,
    reset_decision: bool = False,
) -> None:
    node.review_status = review_status
    structured_content = dict(node.structured_content or {})

    if reset_decision:
        structured_content.pop("answerable", None)
        structured_content.pop("review_note", None)
        structured_content.pop("review_decision_source", None)
        if structured_content.get("review_only_role") == ADMIN_REVIEW_ONLY_ROLE:
            structured_content.pop("review_only_role", None)
            structured_content.pop("review_only", None)
        node.structured_content = structured_content
        return

    if note and note.strip():
        structured_content["review_note"] = note.strip()
    elif note is not None:
        structured_content.pop("review_note", None)

    if review_only is True:
        structured_content["review_only"] = True
        structured_content["review_only_role"] = ADMIN_REVIEW_ONLY_ROLE
        structured_content["answerable"] = False
        structured_content["review_decision_source"] = "admin"
    elif review_only is False and structured_content.get("review_only_role") == ADMIN_REVIEW_ONLY_ROLE:
        structured_content.pop("review_only_role", None)
        structured_content.pop("review_only", None)

    if answerable is not None:
        structured_content["answerable"] = bool(answerable)
        structured_content["review_decision_source"] = "admin"
        if answerable and structured_content.get("review_only_role") == ADMIN_REVIEW_ONLY_ROLE:
            structured_content.pop("review_only_role", None)
            structured_content.pop("review_only", None)

    node.structured_content = structured_content


def _is_parser_review_only(node: LegalKbNode) -> bool:
    structured_content = node.structured_content or {}
    if not bool(structured_content.get("review_only")):
        return False
    return structured_content.get("review_only_role") != ADMIN_REVIEW_ONLY_ROLE


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
