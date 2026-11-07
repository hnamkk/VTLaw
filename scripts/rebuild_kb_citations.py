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

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from src.db.session import async_session_factory  # noqa: E402
from src.legal_kb.retrieval_units import (  # noqa: E402
    build_retrieval_units,
    citation_label_for_node,
    citation_mismatch_for_unit,
    node_is_answerable,
)
from src.models.legal_kb import (  # noqa: E402
    LegalKbRevision,
    LegalKbRetrievalUnit,
    LegalKbReviewEvent,
)


@dataclass
class CitationRebuildReport:
    revision_id: str
    document_number: str | None
    title: str | None
    publication_status: str
    retrieval_units: int
    active_units: int
    mismatched_units: int
    labels_to_change: int
    answerable_nodes: int
    rebuilt: bool
    skipped_reason: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit hoặc rebuild citation_label cho KB hiện hành. "
            "Mặc định là dry-run và không ghi dữ liệu."
        )
    )
    parser.add_argument(
        "--document-number",
        action="append",
        default=[],
        help="Chỉ xử lý văn bản có số hiệu này. Có thể truyền nhiều lần.",
    )
    parser.add_argument(
        "--revision-id",
        action="append",
        default=[],
        help="Chỉ xử lý revision_id này. Có thể truyền nhiều lần.",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Bao gồm cả revision draft/archived. Mặc định chỉ published/suspended.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Thực sự rebuild retrieval units. Nếu không có cờ này, script chỉ audit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="In report dạng JSON.",
    )
    return parser.parse_args()


async def _load_revisions(
    *,
    document_numbers: set[str],
    revision_ids: set[str],
    include_drafts: bool,
) -> list[LegalKbRevision]:
    async with async_session_factory() as session:
        stmt = (
            select(LegalKbRevision)
            .options(
                selectinload(LegalKbRevision.document),
                selectinload(LegalKbRevision.canonical_nodes),
                selectinload(LegalKbRevision.retrieval_units).selectinload(
                    LegalKbRetrievalUnit.canonical_node
                ),
            )
            .order_by(LegalKbRevision.created_at)
        )
        if not include_drafts:
            stmt = stmt.where(LegalKbRevision.publication_status.in_(("published", "suspended")))
        if revision_ids:
            stmt = stmt.where(LegalKbRevision.revision_id.in_(revision_ids))
        result = await session.execute(stmt)
        revisions = list(result.scalars().unique().all())
        if document_numbers:
            filters = {value.lower() for value in document_numbers}
            revisions = [
                revision
                for revision in revisions
                if any(value in (revision.document.document_number or "").lower() for value in filters)
            ]
        return revisions


def _audit_revision(revision: LegalKbRevision) -> tuple[int, int, int, int]:
    parent_map = {node.node_id: node for node in revision.canonical_nodes}
    expected_by_node_id = {
        node.node_id: citation_label_for_node(node=node, parent_map=parent_map)
        for node in revision.canonical_nodes
    }
    mismatched_units = 0
    labels_to_change = 0
    active_units = 0
    for unit in revision.retrieval_units:
        if unit.answerable_status == "active":
            active_units += 1
        if unit.canonical_node is not None:
            mismatch = citation_mismatch_for_unit(
                node=unit.canonical_node,
                citation_label=unit.citation_label,
            )
            if mismatch:
                mismatched_units += 1
        expected_label = expected_by_node_id.get(unit.canonical_node_id)
        if expected_label and unit.citation_label != expected_label:
            labels_to_change += 1
    answerable_nodes = sum(
        1
        for node in revision.canonical_nodes
        if node.review_status == "approved" and node_is_answerable(node)
    )
    return active_units, mismatched_units, labels_to_change, answerable_nodes


async def rebuild_citations(
    *,
    document_numbers: set[str],
    revision_ids: set[str],
    include_drafts: bool,
    dry_run: bool,
) -> list[CitationRebuildReport]:
    reports: list[CitationRebuildReport] = []
    revisions = await _load_revisions(
        document_numbers=document_numbers,
        revision_ids=revision_ids,
        include_drafts=include_drafts,
    )

    async with async_session_factory() as session:
        for loaded_revision in revisions:
            revision = await session.get(
                LegalKbRevision,
                loaded_revision.revision_id,
                options=[
                    selectinload(LegalKbRevision.document),
                    selectinload(LegalKbRevision.canonical_nodes),
                    selectinload(LegalKbRevision.retrieval_units).selectinload(
                        LegalKbRetrievalUnit.canonical_node
                    ),
                ],
            )
            if revision is None:
                continue
            active_units, mismatched_units, labels_to_change, answerable_nodes = _audit_revision(
                revision
            )
            skipped_reason = None
            rebuilt = False
            if answerable_nodes == 0:
                skipped_reason = "Không có mục nội dung nào được dùng cho hỏi đáp."
            elif not dry_run and (mismatched_units or labels_to_change):
                generated = await build_retrieval_units(
                    document=revision.document,
                    revision=revision,
                )
                if generated.answerable_count == 0:
                    skipped_reason = "Không sinh được retrieval unit dùng cho hỏi đáp."
                else:
                    await session.execute(
                        delete(LegalKbRetrievalUnit).where(
                            LegalKbRetrievalUnit.revision_id == revision.revision_id
                        )
                    )
                    for unit in generated.units:
                        session.add(unit)
                    session.add(
                        LegalKbReviewEvent(
                            review_event_id=str(uuid4()),
                            document_id=revision.document_id,
                            revision_id=revision.revision_id,
                            entity_type="revision",
                            entity_id=revision.revision_id,
                            decision="updated",
                            actor_user_id=None,
                            details={
                                "action": "rebuild_legal_kb_citations",
                                "retrieval_units": len(generated.units),
                                "answerable_units": generated.answerable_count,
                                "previous_mismatched_units": mismatched_units,
                                "previous_labels_to_change": labels_to_change,
                            },
                        )
                    )
                    rebuilt = True
            reports.append(
                CitationRebuildReport(
                    revision_id=revision.revision_id,
                    document_number=revision.document.document_number,
                    title=revision.document.title,
                    publication_status=revision.publication_status,
                    retrieval_units=len(revision.retrieval_units),
                    active_units=active_units,
                    mismatched_units=mismatched_units,
                    labels_to_change=labels_to_change,
                    answerable_nodes=answerable_nodes,
                    rebuilt=rebuilt,
                    skipped_reason=skipped_reason,
                )
            )
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return reports


def _print_reports(reports: list[CitationRebuildReport], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([report.__dict__ for report in reports], ensure_ascii=False, indent=2))
        return
    for report in reports:
        status = "rebuilt" if report.rebuilt else "dry-run"
        if report.skipped_reason:
            status = f"skipped: {report.skipped_reason}"
        print(
            f"{report.document_number or '(không số hiệu)'} | {report.publication_status} | "
            f"units={report.retrieval_units} | active={report.active_units} | "
            f"mismatch={report.mismatched_units} | label_changes={report.labels_to_change} | "
            f"answerable_nodes={report.answerable_nodes} | {status}"
        )


async def _main() -> None:
    args = _parse_args()
    reports = await rebuild_citations(
        document_numbers=set(args.document_number),
        revision_ids=set(args.revision_id),
        include_drafts=args.include_drafts,
        dry_run=not args.apply,
    )
    _print_reports(reports, as_json=args.json)


if __name__ == "__main__":
    asyncio.run(_main())
