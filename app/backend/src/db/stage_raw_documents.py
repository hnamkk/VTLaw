"""Stage raw documents into the HITL queue; never activate them directly."""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import async_session_factory
from src.models.document_chunk import DocumentChunk
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument
from src.rag.ingestion import ingest_document
from src.rag.inventory import (
    DEFAULT_MANIFEST,
    DEFAULT_RAW_DIR,
    load_manifest,
    sha256_file,
    validate_raw_inventory,
)
from src.rag.metadata_extraction import extract_effective_date_candidate
from src.rag.parsing import parse_document

_DOC_TYPE_BY_TOKEN = {
    "QH": "LUAT",
    "QH14": "LUAT",
    "QH15": "LUAT",
    "ND-CP": "NGHI_DINH",
    "TT-BGTVT": "THONG_TU",
    "TT-BXD": "THONG_TU",
    "VBHN-BCA": "CONG_VAN",
    "VBHN-BGTVT": "CONG_VAN",
    "VBHN-BXD": "CONG_VAN",
    "VBHN-VPQH": "CONG_VAN",
}
_ISSUER_BY_TOKEN = {
    "QH": "Quoc hoi",
    "QH14": "Quoc hoi",
    "QH15": "Quoc hoi",
    "ND-CP": "Chinh phu",
    "TT-BGTVT": "Bo Giao thong van tai",
    "TT-BXD": "Bo Xay dung",
    "VBHN-BCA": "Bo Cong an",
    "VBHN-BGTVT": "Bo Giao thong van tai",
    "VBHN-BXD": "Bo Xay dung",
    "VBHN-VPQH": "Van phong Quoc hoi",
}


def _normalize_number(value: str) -> str:
    return value.replace("_", "/").strip("/")


def _infer_number_from_filename(path: Path) -> str:
    stem = path.stem
    # Drop the trailing source id in names like 100_2019_ND-CP_426369.docx.
    stem = re.sub(r"_\d{5,}$", "", stem)
    if re.match(
        r"^(?:\d+_\d{4}_[A-Z0-9-]+|\d+_VBHN-[A-Z0-9-]+)$",
        stem,
        flags=re.IGNORECASE,
    ):
        return _normalize_number(stem.upper())
    return stem


def _infer_token(document_number: str) -> str | None:
    upper = document_number.upper()
    for token in sorted(_DOC_TYPE_BY_TOKEN, key=len, reverse=True):
        if token in upper:
            return token
    return None


def _infer_title(entry: dict[str, Any], path: Path, document_number: str, doc_type: str) -> str:
    if entry.get("title"):
        return entry["title"]
    if doc_type == "QUY_CHUAN":
        return document_number if "QCVN" in document_number.upper() else f"Quy chuan {document_number}"
    if "/VBHN-" in document_number.upper():
        return f"Van ban hop nhat {document_number}"
    label = {
        "LUAT": "Luat",
        "BO_LUAT": "Bo luat",
        "NGHI_DINH": "Nghi dinh",
        "THONG_TU": "Thong tu",
        "QUYET_DINH": "Quyet dinh",
        "CONG_VAN": "Cong van",
    }.get(doc_type, "Van ban")
    return f"{label} {document_number or path.stem}"


def entry_for_raw_file(path: Path, manifest_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return staging metadata for a raw file.

    Manifest metadata wins when present. For files not listed in the manifest,
    this function infers conservative metadata from the filename so the document
    can still enter HITL review instead of being silently blocked.
    """
    entry: dict[str, Any] = dict(manifest_entry or {})
    checksum = entry.get("sha256") or sha256_file(path)
    document_number = entry.get("document_number") or _infer_number_from_filename(path)
    token = _infer_token(document_number)
    parser_profile = entry.get("parser_profile")
    if not parser_profile:
        lower_name = path.stem.lower()
        parser_profile = "qcvn" if "qcvn" in lower_name or "quy chuan" in lower_name else "legal"
    doc_type = entry.get("doc_type")
    if not doc_type:
        doc_type = "QUY_CHUAN" if parser_profile == "qcvn" else _DOC_TYPE_BY_TOKEN.get(token or "", "CONG_VAN")

    entry.update(
        {
            "filename": path.name,
            "sha256": checksum,
            "document_number": document_number,
            "title": _infer_title(entry, path, document_number, doc_type),
            "doc_type": doc_type,
            "issuer": entry.get("issuer") or _ISSUER_BY_TOKEN.get(token or "", "Chua xac minh"),
            "corpus": entry.get("corpus") or ("road_technical" if parser_profile == "qcvn" else "road_law"),
            "rag_scope": entry.get("rag_scope") or "enabled",
            "parser_profile": parser_profile,
            "official_source_url": entry.get("official_source_url"),
            "official_status": entry.get("official_status") or "review_required",
            "inferred_metadata": manifest_entry is None,
        }
    )
    return entry


def discover_stage_entries(
    raw_dir: Path = DEFAULT_RAW_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> tuple[list[tuple[dict[str, Any], Path]], list[str], list[str]]:
    inventory = validate_raw_inventory(raw_dir, manifest_path)
    manifest = load_manifest(manifest_path)
    manifest_by_name = {item["filename"]: item for item in manifest["documents"]}
    entries = [
        (entry_for_raw_file(raw_dir / filename, manifest_by_name.get(filename)), raw_dir / filename)
        for filename in inventory.valid_files
    ]
    return entries, inventory.warnings, inventory.errors


def _effective_date(path: Path, entry: dict[str, Any]) -> date | None:
    if entry.get("valid_from"):
        return date.fromisoformat(entry["valid_from"])
    parsed = parse_document(str(path))
    text = "\n".join(block.text for block in parsed.blocks)
    return extract_effective_date_candidate(text)


async def _process_staged_document(
    session: AsyncSession,
    document: LegalDocument,
    queue: KbUpdateQueue,
    path: Path,
) -> bool:
    """Process one pending document without poisoning the surrounding batch."""
    queue_id = queue.queue_id
    try:
        report = await ingest_document(session, document.doc_id, str(path))
        queue.processing_status = "ready"
        queue.processing_error = None
        queue.parser_confidence = report.parser_confidence
        queue.warning_messages = list(queue.warning_messages or []) + report.warnings
    except Exception as exc:
        await session.rollback()
        queue = await session.get(KbUpdateQueue, queue_id)
        if queue is None:
            return False
        queue.processing_status = "failed"
        queue.processing_error = str(exc)
    await session.commit()
    return queue.processing_status == "ready"


async def stage_documents(confirm: bool, process: bool) -> int:
    entries, warnings, errors = discover_stage_entries()
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    prepared: list[tuple[dict[str, Any], Path, date]] = []
    for entry, path in entries:
        effective = _effective_date(path, entry)
        if effective is None:
            print(f"BLOCKED: {entry['filename']} has no effective-date candidate for reviewer.")
            continue
        prepared.append((entry, path, effective))
        print(
            f"READY: {entry['document_number']} | {entry['corpus']} | "
            f"{entry['rag_scope']} | candidate={effective.isoformat()}"
        )

    if not confirm:
        print(f"DRY-RUN: {len(prepared)}/{len(entries)} available raw documents ready to stage.")
        return 0 if len(prepared) == len(entries) else 2

    failed_count = 0
    async with async_session_factory() as session:
        for entry, path, effective in prepared:
            existing = await session.scalar(
                select(LegalDocument).where(
                    LegalDocument.source_checksum == entry["sha256"],
                    LegalDocument.source_version == 1,
                )
            )
            if existing is not None:
                queue = await session.scalar(
                    select(KbUpdateQueue)
                    .where(
                        KbUpdateQueue.doc_id == existing.doc_id,
                        KbUpdateQueue.review_status == "pending",
                    )
                    .order_by(KbUpdateQueue.created_at.desc())
                )
                has_chunks = await session.scalar(
                    select(DocumentChunk.chunk_id)
                    .where(DocumentChunk.doc_id == existing.doc_id)
                    .limit(1)
                )
                retryable = bool(
                    process
                    and queue is not None
                    and (
                        queue.processing_status in {"queued", "failed"}
                        or has_chunks is None
                    )
                )
                if not retryable:
                    print(f"SKIP: {entry['filename']} already staged with this checksum.")
                    continue
                document = existing
                # A retry may use a newly completed manifest entry. Refresh
                # pending metadata before rebuilding chunks, never active data.
                document.title = entry["title"]
                document.document_number = entry["document_number"]
                document.document_family = entry["corpus"]
                document.doc_type = entry["doc_type"]
                document.issuer = entry["issuer"]
                document.source_url = entry.get("official_source_url")
                document.effective_date = effective
                document.valid_from = effective
                document.rag_scope = entry["rag_scope"]
                document.rag_enabled = entry["rag_scope"] != "disabled"
                document.parser_profile = entry["parser_profile"]
                document.parser_version = (
                    "qcvn-v1" if entry["parser_profile"] == "qcvn" else "legal-v2"
                )
                document.domain_tags = [entry["corpus"]]
                queue.processing_status = "queued"
                queue.processing_error = None
                queue.source_file_name = path.name
                queue.source_path = str(path.resolve())
                await session.commit()
                print(f"RETRY: {entry['filename']}")
            else:
                legal_status = entry.get("official_status")
                if legal_status not in {
                    "future_effective",
                    "active",
                    "partially_repealed",
                    "repealed",
                }:
                    legal_status = "future_effective" if effective > date.today() else "active"
                document = LegalDocument(
                    title=entry["title"],
                    document_number=entry["document_number"],
                    document_family=entry["corpus"],
                    doc_type=entry["doc_type"],
                    status="pending_review",
                    review_status="pending",
                    legal_status=legal_status,
                    rag_scope=entry["rag_scope"],
                    rag_enabled=entry["rag_scope"] != "disabled",
                    effective_date=effective,
                    valid_from=effective,
                    issuer=entry["issuer"],
                    source_url=entry.get("official_source_url"),
                    source_checksum=entry["sha256"],
                    parser_profile=entry["parser_profile"],
                    parser_version="qcvn-v1" if entry["parser_profile"] == "qcvn" else "legal-v2",
                    domain_tags=[entry["corpus"]],
                )
                session.add(document)
                await session.flush()
                queue = KbUpdateQueue(
                    doc_id=document.doc_id,
                    change_type="create",
                    review_status="pending",
                    processing_status="queued" if process else "ready",
                    source_file_name=path.name,
                    source_path=str(path.resolve()),
                    extracted_metadata={
                        "manifest_version": 1,
                        "effective_date_candidate": effective.isoformat(),
                        "official_status_candidate": entry.get("official_status"),
                        "corpus": entry["corpus"],
                        "rag_scope": entry["rag_scope"],
                        "inferred_metadata": entry.get("inferred_metadata", False),
                    },
                    warning_messages=(
                        ["Metadata was inferred from file name; reviewer must verify."]
                        if entry.get("inferred_metadata")
                        else []
                    ),
                )
                session.add(queue)
                await session.commit()
            if process:
                processed = await _process_staged_document(session, document, queue, path)
                if not processed:
                    failed_count += 1
                    print(f"FAILED: {entry['filename']} | see queue processing_error")
                else:
                    print(f"PROCESSED: {entry['filename']}")
            else:
                print(f"STAGED: {entry['filename']}")
    return 1 if failed_count else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--process",
        action="store_true",
        help="Parse and embed after staging. This calls the configured embedding provider.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(stage_documents(args.confirm, args.process)))


if __name__ == "__main__":
    main()
