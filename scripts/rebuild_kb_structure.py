from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from src.db.session import async_session_factory  # noqa: E402
from src.legal_kb.ingestion import _legal_kb_local_root  # noqa: E402
from src.legal_kb.parser import build_canonical_nodes, parse_docx_into_artifacts  # noqa: E402
from src.legal_kb.retrieval_units import (  # noqa: E402
    _answerable_status,
    _content_hash,
    _embedding_text,
    citation_label_for_node,
    node_is_answerable,
)
from src.models.legal_kb import (  # noqa: E402
    LegalKbAmendmentOperation,
    LegalKbNode,
    LegalKbRevision,
    LegalKbProvisionSource,
    LegalKbReviewEvent,
    LegalKbSourceAsset,
)
from src.rag.embedding import embed_texts  # noqa: E402


def _source_path(storage_uri: str) -> Path | None:
    if not storage_uri or "://" in storage_uri and not storage_uri.startswith("file:///"):
        return None
    path = Path(storage_uri.removeprefix("file:///"))
    return path if path.is_absolute() else (_legal_kb_local_root() / path).resolve()


def _map_projected_nodes(
    existing: list[LegalKbNode],
    projected: list[LegalKbNode],
) -> tuple[dict[str, LegalKbNode], list[LegalKbNode]]:
    mapped: dict[str, LegalKbNode] = {}
    inserted: list[LegalKbNode] = []
    existing_index = 0
    for candidate in projected:
        if (
            existing_index < len(existing)
            and (existing[existing_index].text or "").strip() == (candidate.text or "").strip()
        ):
            mapped[candidate.node_id] = existing[existing_index]
            existing_index += 1
        elif bool((candidate.structured_content or {}).get("structural_only")):
            inserted.append(candidate)
        else:
            raise RuntimeError(
                f"Cấu trúc nguồn lệch tại node dự kiến {candidate.order_index}; dừng để không ghi sai dữ liệu."
            )
    if existing_index != len(existing):
        raise RuntimeError("Không ánh xạ được toàn bộ node hiện có; dừng để không ghi sai dữ liệu.")
    return mapped, inserted


def _review_state(existing: LegalKbNode, projected: LegalKbNode) -> tuple[str, dict]:
    structured = dict(projected.structured_content or {})
    old_structured = dict(existing.structured_content or {})
    if structured.get("review_only"):
        return "approved", structured
    if old_structured.get("review_only_role") == "admin_review_only":
        structured.update(review_only=True, review_only_role="admin_review_only", answerable=False)
        return "approved", structured
    if existing.review_status == "rejected":
        return "rejected", structured
    return "approved", structured


async def rebuild_revision(*, revision_id: str, apply: bool) -> dict:
    async with async_session_factory() as session:
        revision = await session.get(
            LegalKbRevision,
            revision_id,
            options=[
                selectinload(LegalKbRevision.document),
                selectinload(LegalKbRevision.canonical_nodes),
                selectinload(LegalKbRevision.retrieval_units),
            ],
        )
        if revision is None:
            raise RuntimeError("Không tìm thấy revision cần rebuild.")
        source_asset = await session.get(LegalKbSourceAsset, revision.source_asset_id)
        source_path = _source_path(source_asset.storage_uri if source_asset else "")
        if source_path is None or not source_path.exists():
            raise RuntimeError("Không tìm thấy file nguồn cục bộ của revision.")

        dependent_sources = await session.scalar(
            select(func.count()).select_from(LegalKbProvisionSource).where(
                LegalKbProvisionSource.canonical_node_id.in_(
                    select(LegalKbNode.node_id).where(
                        LegalKbNode.revision_id == revision_id
                    )
                )
            )
        )
        dependent_operations = await session.scalar(
            select(func.count()).select_from(LegalKbAmendmentOperation).where(
                LegalKbAmendmentOperation.source_canonical_node_id.in_(
                    select(LegalKbNode.node_id).where(
                        LegalKbNode.revision_id == revision_id
                    )
                )
            )
        )
        if dependent_sources or dependent_operations:
            raise RuntimeError("Revision có liên kết phiên bản điều khoản; không thể rebuild tự động.")

        artifacts = parse_docx_into_artifacts(
            source_path=str(source_path),
            title=revision.document.title or source_asset.original_filename,
        )
        projected = build_canonical_nodes(
            revision_id=revision_id,
            drafts=artifacts.drafts,
            parser_confidence=artifacts.parsed.confidence,
        )
        existing = sorted(revision.canonical_nodes, key=lambda node: node.order_index)
        mapped, inserted = _map_projected_nodes(existing, projected)
        report = {
            "revision_id": revision_id,
            "document_number": revision.document.document_number,
            "old_nodes": len(existing),
            "new_nodes": len(projected),
            "inserted_structural_nodes": len(inserted),
            "old_answerable_units": sum(
                1 for unit in revision.retrieval_units if unit.answerable_status == "active"
            ),
        }
        if not apply:
            await session.rollback()
            return report

        id_map = {projected_id: node.node_id for projected_id, node in mapped.items()}
        id_map.update({node.node_id: node.node_id for node in inserted})
        desired_parents: dict[str, str | None] = {}
        for candidate in projected:
            parent_id = id_map.get(candidate.parent_id) if candidate.parent_id else None
            if candidate.node_id in mapped:
                current = mapped[candidate.node_id]
                review_status, structured = _review_state(current, candidate)
                current.parent_id = None
                current.node_type = candidate.node_type
                current.label = candidate.label
                current.text = candidate.text
                current.order_index = candidate.order_index
                current.provenance = dict(candidate.provenance or {})
                current.structured_content = structured
                current.review_status = review_status
                desired_parents[current.node_id] = parent_id
            else:
                candidate.parent_id = None
                candidate.review_status = "approved"
                session.add(candidate)
                desired_parents[candidate.node_id] = parent_id

        await session.flush()
        parent_map = {node.node_id: node for node in [*existing, *inserted]}
        for node_id, parent_id in desired_parents.items():
            parent_map[node_id].parent_id = parent_id
        await session.flush()
        missing_embedding_units = []
        for unit in revision.retrieval_units:
            node = parent_map[unit.canonical_node_id]
            citation = citation_label_for_node(node=node, parent_map=parent_map)
            answerable = node_is_answerable(node)
            text = _embedding_text(document=revision.document, node=node, citation_label=citation)
            unit.citation_label = citation
            unit.text = text
            unit.answerable_status = (
                _answerable_status(document=revision.document) if answerable else "not_answerable"
            )
            unit.content_hash = _content_hash(
                document=revision.document,
                node=node,
                citation_label=citation,
                text=text,
            )
            unit.metadata_json = {
                "node_type": node.node_type,
                "label": node.label,
                "order_index": node.order_index,
                "answerable": answerable,
            }
            if not answerable:
                unit.embedding_vector = None
                unit.embedding_model = None
                unit.embedding_version = None
            elif unit.embedding_vector is None:
                missing_embedding_units.append(unit)

        if missing_embedding_units:
            vectors = await embed_texts([unit.text for unit in missing_embedding_units])
            for unit, vector in zip(missing_embedding_units, vectors, strict=True):
                unit.embedding_vector = vector
                unit.embedding_model = "text-embedding-3-small"
                unit.embedding_version = "legal_kb_v1"

        report["new_answerable_units"] = sum(
            1 for unit in revision.retrieval_units if unit.answerable_status == "active"
        )
        report["embedded_units"] = len(missing_embedding_units)
        session.add(
            LegalKbReviewEvent(
                review_event_id=str(uuid4()),
                document_id=revision.document_id,
                revision_id=revision_id,
                entity_type="revision",
                entity_id=revision_id,
                decision="updated",
                actor_user_id=None,
                details={"action": "rebuild_legal_kb_structure", **report},
            )
        )
        await session.commit()
        return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-id", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    report = await rebuild_revision(revision_id=args.revision_id, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
