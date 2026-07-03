"""Tests for raw storage discovery and staging metadata."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.db.stage_raw_documents as staging
from src.db.stage_raw_documents import discover_stage_entries, entry_for_raw_file
from src.models.kb_update_queue import KbUpdateQueue
from src.rag.inventory import sha256_file, validate_raw_inventory


def _write_docx(path: Path, body: str = "<w:document/>") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", body)


def _write_manifest(path: Path, documents: list[dict]) -> None:
    path.write_text(json.dumps({"manifest_version": 1, "documents": documents}), encoding="utf-8")


def test_inventory_warns_for_missing_manifest_files_but_keeps_present_files(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    present = raw_dir / "10_2020_ND-CP_315260.docx"
    _write_docx(present)
    missing = "336_2025_ND-CP_670893.docx"
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(
        manifest_path,
        [
            {
                "filename": present.name,
                "sha256": sha256_file(present),
            },
            {"filename": missing, "sha256": "0" * 64},
        ],
    )

    report = validate_raw_inventory(raw_dir, manifest_path)

    assert report.ok is True
    assert report.valid_files == [present.name]
    assert any(missing in warning for warning in report.warnings)


def test_inventory_accepts_supported_raw_file_not_listed_in_manifest(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = raw_dir / "22_2026_TT-BGTVT_123456.docx"
    _write_docx(source)
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(manifest_path, [])

    report = validate_raw_inventory(raw_dir, manifest_path)

    assert report.ok is True
    assert report.valid_files == [source.name]
    assert "not listed in manifest" in report.warnings[0]


def test_entry_for_raw_file_infers_metadata_when_manifest_is_absent(tmp_path):
    source = tmp_path / "22_2026_TT-BGTVT_123456.docx"
    _write_docx(source)

    entry = entry_for_raw_file(source)

    assert entry["filename"] == source.name
    assert entry["document_number"] == "22/2026/TT-BGTVT"
    assert entry["doc_type"] == "THONG_TU"
    assert entry["issuer"] == "Bo Giao thong van tai"
    assert entry["inferred_metadata"] is True


def test_entry_for_consolidated_file_infers_vbhn_identity(tmp_path):
    source = tmp_path / "02_VBHN-BGTVT_572773.docx"
    _write_docx(source)

    entry = entry_for_raw_file(source)

    assert entry["document_number"] == "02/VBHN-BGTVT"
    assert entry["title"] == "Van ban hop nhat 02/VBHN-BGTVT"
    assert entry["doc_type"] == "CONG_VAN"
    assert entry["issuer"] == "Bo Giao thong van tai"
    assert entry["inferred_metadata"] is True


@pytest.mark.asyncio
async def test_processing_failure_rolls_back_and_marks_queue_failed(monkeypatch, tmp_path):
    queue = SimpleNamespace(
        queue_id="queue-1",
        processing_status="queued",
        processing_error=None,
        parser_confidence=None,
        warning_messages=[],
    )

    class FakeSession:
        def __init__(self):
            self.rolled_back = False
            self.commits = 0

        async def rollback(self):
            self.rolled_back = True

        async def get(self, model, queue_id):
            assert self.rolled_back is True
            assert model is KbUpdateQueue
            assert queue_id == queue.queue_id
            return queue

        async def commit(self):
            self.commits += 1

    async def fail_ingestion(session, doc_id, file_path):
        raise ValueError("invalid chunk hierarchy")

    monkeypatch.setattr(staging, "ingest_document", fail_ingestion)
    session = FakeSession()

    processed = await staging._process_staged_document(
        session,
        SimpleNamespace(doc_id="doc-1"),
        queue,
        tmp_path / "source.docx",
    )

    assert processed is False
    assert session.rolled_back is True
    assert session.commits == 1
    assert queue.processing_status == "failed"
    assert queue.processing_error == "invalid chunk hierarchy"


def test_discover_stage_entries_uses_all_valid_files_in_raw_dir(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    manifest_file = raw_dir / "10_2020_ND-CP_315260.docx"
    inferred_file = raw_dir / "22_2026_TT-BGTVT_123456.docx"
    _write_docx(manifest_file)
    _write_docx(inferred_file)
    manifest_path = tmp_path / "manifest.yaml"
    checksum = sha256_file(manifest_file)
    _write_manifest(
        manifest_path,
        [
            {
                "filename": manifest_file.name,
                "sha256": checksum,
                "document_number": "10/2020/ND-CP",
                "title": "Nghi dinh 10/2020/ND-CP",
                "doc_type": "NGHI_DINH",
                "issuer": "Chinh phu",
                "corpus": "road_law",
                "rag_scope": "enabled",
                "parser_profile": "legal",
                "official_status": "review_required",
            }
        ],
    )

    entries, warnings, errors = discover_stage_entries(raw_dir, manifest_path)

    assert errors == []
    assert len(entries) == 2
    assert {entry["filename"] for entry, _ in entries} == {manifest_file.name, inferred_file.name}
    assert any("not listed in manifest" in warning for warning in warnings)


def test_discover_stage_entries_scales_with_arbitrary_raw_file_count(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    file_count = 17
    for index in range(file_count):
        _write_docx(raw_dir / f"{index + 1:02d}_2026_TT-BGTVT_{100000 + index}.docx")
    manifest_path = tmp_path / "manifest.yaml"
    _write_manifest(manifest_path, [])

    entries, warnings, errors = discover_stage_entries(raw_dir, manifest_path)

    assert errors == []
    assert len(entries) == file_count
    assert len(warnings) == file_count
    assert all(entry["inferred_metadata"] for entry, _ in entries)


def test_eval_alias_resolution_uses_generated_document_ids():
    from eval.run_eval import build_expected_doc_map, unavailable_expected_docs
    from eval.schemas import EvalCase

    documents = [
        SimpleNamespace(
            doc_id="generated-nd10",
            status="active",
            document_number="10/2020/NĐ-CP",
            title="Nghị định 10/2020/NĐ-CP",
        ),
        SimpleNamespace(
            doc_id="generated-nd100",
            status="pending_review",
            document_number="100/2019/NĐ-CP",
            title="Nghị định 100/2019/NĐ-CP",
        ),
    ]

    doc_map = build_expected_doc_map(documents, aliases={"doc-nd10-2020", "doc-nd100-2019"})
    active_case = EvalCase(
        case_id="case-1",
        category="active_law_qa",
        question="q",
        expected_behavior="answer",
        expected_doc_ids=["doc-nd10-2020"],
    )
    pending_case = EvalCase(
        case_id="case-2",
        category="active_law_qa",
        question="q",
        expected_behavior="answer",
        expected_doc_ids=["doc-nd100-2019"],
    )

    assert doc_map["doc-nd10-2020"].doc_id == "generated-nd10"
    assert unavailable_expected_docs(active_case, doc_map) == []
    assert unavailable_expected_docs(pending_case, doc_map) == ["doc-nd100-2019:pending_review"]


def test_eval_alias_resolution_supports_new_document_aliases_without_code_changes():
    from eval.run_eval import build_expected_doc_map

    documents = [
        SimpleNamespace(
            doc_id="generated-tt22",
            status="active",
            doc_type="THONG_TU",
            document_number="22/2026/TT-BGTVT",
            title="Thong tu 22/2026/TT-BGTVT",
        ),
        SimpleNamespace(
            doc_id="generated-luat99",
            status="active",
            doc_type="LUAT",
            document_number="99/2027/QH16",
            title="Luat 99/2027/QH16",
        ),
    ]

    doc_map = build_expected_doc_map(
        documents,
        aliases={"doc-tt-22-2026", "doc-luat-99-2027"},
    )

    assert doc_map["doc-tt-22-2026"].doc_id == "generated-tt22"
    assert doc_map["doc-luat-99-2027"].doc_id == "generated-luat99"
