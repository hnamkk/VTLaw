from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.legal_kb.ingestion import _legal_kb_local_root
from src.legal_kb.parser import build_canonical_nodes, parse_docx_into_artifacts
from src.legal_kb.retrieval_units import (
    RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION,
    build_retrieval_units,
)
from src.models.legal_kb import (
    LegalKbNode,
    LegalKbRevision,
    LegalKbReviewEvent,
    LegalKbSourceAsset,
    LegalKbRetrievalUnit,
)
from src.db.session import async_session_factory

ADMIN_REVIEW_ONLY_ROLE = "admin_review_only"


@dataclass
class RevisionUpdateReport:
    revision_id: str
    document_number: str | None
    title: str | None
    node_count: int
    changed_nodes: int
    rebuilt_retrieval_units: bool
    skipped_reason: str | None = None


def _resolve_local_source_path(storage_uri: str) -> Path | None:
    if not storage_uri:
        return None
    if storage_uri.startswith("file:///"):
        return Path(storage_uri.removeprefix("file:///"))
    if "://" in storage_uri:
        return None
    return Path(storage_uri)


def _apply_parser_policy(existing: LegalKbNode, projected: LegalKbNode) -> tuple[dict, str]:
    existing_structured = dict(existing.structured_content or {})
    projected_structured = dict(projected.structured_content or {})

    if existing_structured.get("review_only_role") == ADMIN_REVIEW_ONLY_ROLE:
        projected_structured["review_only"] = True
        projected_structured["review_only_role"] = ADMIN_REVIEW_ONLY_ROLE
        projected_structured["answerable"] = False
    elif (
        existing.review_status == "approved"
        and existing.node_type in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION
        and "answerable" in existing_structured
        and not existing_structured.get("review_only")
    ):
        projected_structured["answerable"] = existing_structured["answerable"]

    if existing.review_status == "rejected":
        review_status = "rejected"
    elif projected_structured.get("review_only"):
        review_status = "approved"
    elif (
        projected.node_type in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION
        and "answerable" in projected_structured
    ):
        review_status = "approved"
    elif projected.node_type not in RISKY_NODE_TYPES_REQUIRING_ANSWERABILITY_DECISION:
        review_status = "approved"
    else:
        review_status = existing.review_status

    return projected_structured, review_status


async def _load_revisions(*, revision_ids: set[str] | None) -> list[LegalKbRevision]:
    async with async_session_factory() as session:
        stmt = (
            select(LegalKbRevision)
            .options(
                selectinload(LegalKbRevision.document),
                selectinload(LegalKbRevision.source_assets),
                selectinload(LegalKbRevision.canonical_nodes),
                selectinload(LegalKbRevision.retrieval_units),
            )
            .order_by(LegalKbRevision.created_at)
        )
        if revision_ids:
            stmt = stmt.where(LegalKbRevision.revision_id.in_(revision_ids))
        result = await session.execute(stmt)
        return list(result.scalars().unique().all())


async def reapply_policy(*, revision_ids: set[str] | None, dry_run: bool) -> list[RevisionUpdateReport]:
    reports: list[RevisionUpdateReport] = []
    revisions = await _load_revisions(revision_ids=revision_ids)

    async with async_session_factory() as session:
        for revision in revisions:
            revision = await session.get(
                LegalKbRevision,
                revision.revision_id,
                options=[
                    selectinload(LegalKbRevision.document),
                    selectinload(LegalKbRevision.source_assets),
                    selectinload(LegalKbRevision.canonical_nodes),
                    selectinload(LegalKbRevision.retrieval_units),
                ],
            )
            if revision is None:
                continue
            revision_id = revision.revision_id
            document_id = revision.document_id
            document_number = revision.document.document_number
            title = revision.document.title

            source_asset = next(
                (asset for asset in revision.source_assets if asset.asset_role == "source"),
                None,
            )
            if source_asset is None:
                reports.append(
                    RevisionUpdateReport(
                        revision_id=revision_id,
                        document_number=document_number,
                        title=title,
                        node_count=0,
                        changed_nodes=0,
                        rebuilt_retrieval_units=False,
                        skipped_reason="missing_source_asset",
                    )
                )
                continue

            source_path = _resolve_local_source_path(source_asset.storage_uri)
            if source_path is None:
                reports.append(
                    RevisionUpdateReport(
                        revision_id=revision_id,
                        document_number=document_number,
                        title=title,
                        node_count=len(revision.canonical_nodes),
                        changed_nodes=0,
                        rebuilt_retrieval_units=False,
                        skipped_reason="non_local_storage_uri",
                    )
                )
                continue
            if not source_path.is_absolute():
                source_path = (_legal_kb_local_root() / source_path).resolve()
            if not source_path.exists():
                reports.append(
                    RevisionUpdateReport(
                        revision_id=revision_id,
                        document_number=document_number,
                        title=title,
                        node_count=len(revision.canonical_nodes),
                        changed_nodes=0,
                        rebuilt_retrieval_units=False,
                        skipped_reason=f"missing_source_file:{source_path}",
                    )
                )
                continue

            artifacts = parse_docx_into_artifacts(
                source_path=str(source_path),
                title=revision.document.title or source_asset.original_filename,
            )
            projected_nodes = build_canonical_nodes(
                revision_id=revision.revision_id,
                drafts=artifacts.drafts,
                parser_confidence=artifacts.parsed.confidence,
            )
            existing_nodes = sorted(revision.canonical_nodes, key=lambda node: node.order_index)
            if len(existing_nodes) != len(projected_nodes):
                reports.append(
                    RevisionUpdateReport(
                        revision_id=revision_id,
                        document_number=document_number,
                        title=title,
                        node_count=len(existing_nodes),
                        changed_nodes=0,
                        rebuilt_retrieval_units=False,
                        skipped_reason=f"node_count_mismatch:{len(existing_nodes)}!={len(projected_nodes)}",
                    )
                )
                continue

            by_projected_id = {node.node_id: node for node in projected_nodes}
            old_id_by_order = {node.order_index: node.node_id for node in existing_nodes}
            changed_nodes = 0

            for existing_node, projected_node in zip(existing_nodes, projected_nodes, strict=True):
                if (existing_node.text or "").strip() != (projected_node.text or "").strip():
                    changed_nodes = 0
                    reports.append(
                        RevisionUpdateReport(
                            revision_id=revision_id,
                            document_number=document_number,
                            title=title,
                            node_count=len(existing_nodes),
                            changed_nodes=0,
                            rebuilt_retrieval_units=False,
                            skipped_reason=f"text_mismatch_at_order:{existing_node.order_index}",
                        )
                    )
                    break

                projected_parent_order = None
                if projected_node.parent_id:
                    projected_parent = by_projected_id[projected_node.parent_id]
                    projected_parent_order = projected_parent.order_index
                translated_parent_id = (
                    old_id_by_order.get(projected_parent_order) if projected_parent_order is not None else None
                )
                projected_structured, review_status = _apply_parser_policy(existing_node, projected_node)

                changed = any(
                    [
                        existing_node.parent_id != translated_parent_id,
                        existing_node.node_type != projected_node.node_type,
                        existing_node.label != projected_node.label,
                        (existing_node.provenance or {}) != (projected_node.provenance or {}),
                        (existing_node.structured_content or {}) != projected_structured,
                        existing_node.review_status != review_status,
                    ]
                )
                if changed:
                    changed_nodes += 1

                if dry_run:
                    continue

                existing_node.parent_id = translated_parent_id
                existing_node.node_type = projected_node.node_type
                existing_node.label = projected_node.label
                existing_node.provenance = dict(projected_node.provenance or {})
                existing_node.structured_content = projected_structured
                existing_node.review_status = review_status
            else:
                rebuilt_retrieval_units = False
                if (
                    not dry_run
                    and revision.publication_status in {"published", "suspended"}
                    and not getattr(reapply_policy, "_skip_retrieval_rebuild", False)
                ):
                    generated = await build_retrieval_units(document=revision.document, revision=revision)
                    await session.execute(
                        delete(LegalKbRetrievalUnit).where(LegalKbRetrievalUnit.revision_id == revision_id)
                    )
                    for unit in generated.units:
                        session.add(unit)
                    rebuilt_retrieval_units = True

                if not dry_run and changed_nodes > 0:
                    session.add(
                        LegalKbReviewEvent(
                            review_event_id=str(uuid4()),
                            document_id=document_id,
                            revision_id=revision_id,
                            entity_type="revision",
                            entity_id=revision_id,
                            decision="updated",
                            actor_user_id=None,
                            details={
                                "action": "reapply_legal_kb_parser_policy",
                                "changed_nodes": changed_nodes,
                                "rebuilt_retrieval_units": rebuilt_retrieval_units,
                            },
                        )
                    )
                    await session.commit()
                elif not dry_run:
                    await session.rollback()

                reports.append(
                    RevisionUpdateReport(
                        revision_id=revision_id,
                        document_number=document_number,
                        title=title,
                        node_count=len(existing_nodes),
                        changed_nodes=changed_nodes,
                        rebuilt_retrieval_units=rebuilt_retrieval_units,
                    )
                )
                continue

            if not dry_run:
                await session.rollback()

    return reports


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-id", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-retrieval-rebuild", action="store_true")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    reapply_policy._skip_retrieval_rebuild = args.skip_retrieval_rebuild
    reports = await reapply_policy(
        revision_ids=set(args.revision_id) or None,
        dry_run=args.dry_run,
    )
    for report in reports:
        print(
            json.dumps(
                {
                    "revision_id": report.revision_id,
                    "document_number": report.document_number,
                    "title": report.title,
                    "node_count": report.node_count,
                    "changed_nodes": report.changed_nodes,
                    "rebuilt_retrieval_units": report.rebuilt_retrieval_units,
                    "skipped_reason": report.skipped_reason,
                },
                ensure_ascii=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(_main())
