from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient

from src.api.v1.admin_kb import (
    SavedUpload,
    _collect_document_warnings,
    _duplicate_source_detail,
    _find_duplicate_candidates,
    _queue_item_to_schema,
    _queue_source_path,
    _resolve_upload_target_document,
    _save_upload,
    _structure_summary,
    approve_kb_queue_item,
    reject_kb_queue_item,
    router,
    save_kb_queue_draft,
)
from src.api.v1.schemas import KbQueueApproveRequest, KbQueueDraftRequest, KbQueueRejectRequest
from src.auth.dependencies import require_admin
from src.db.session import get_session
from src.models.document_asset import DocumentAsset
from src.models.document_chunk import DocumentChunk
from src.models.kb_update_queue import KbUpdateQueue
from src.models.legal_document import LegalDocument

# Legacy unit contracts run on an isolated app; production only mounts kho văn bản.
app = FastAPI()
app.include_router(router, prefix="/api/v1")


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.fixture(autouse=True)
def admin_dependency_override():
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        user_id="11111111-1111-1111-1111-111111111111",
        role="ADMIN",
        is_active=True,
    )
    yield
    app.dependency_overrides.pop(require_admin, None)


def test_collect_document_warnings_flags_missing_source_and_low_parser_confidence():
    document = LegalDocument(
        doc_id="doc-1",
        title="Thong tu test",
        doc_type="THONG_TU",
        status="pending_review",
        effective_date=date(2026, 9, 1),
        issuer="Bo GTVT",
        source_url=None,
        domain_tags=[],
    )
    chunks = [
        DocumentChunk(
            doc_id="doc-1",
            text_content="Noi dung chunk",
            chunk_type="dieu",
            article_num=1,
            status="pending_review",
            effective_date=date(2026, 9, 1),
            metadata_json={"parser_confidence": 0.42, "display_path": "Dieu 1"},
        )
    ]

    warnings = _collect_document_warnings(document, chunks)

    assert "Parser confidence dưới ngưỡng, cần duyệt kỹ." in warnings


def test_structure_summary_counts_article_clause_and_point_units():
    chunks = [
        DocumentChunk(
            doc_id="doc-1",
            text_content="A",
            chunk_type="dieu",
            article_num=1,
            clause_num=1,
            point_num="a",
            status="pending_review",
            effective_date=date(2026, 9, 1),
            metadata_json={},
        ),
        DocumentChunk(
            doc_id="doc-1",
            text_content="B",
            chunk_type="dieu",
            article_num=1,
            clause_num=2,
            status="pending_review",
            effective_date=date(2026, 9, 1),
            metadata_json={},
        ),
        DocumentChunk(
            doc_id="doc-1",
            text_content="C",
            chunk_type="dieu",
            article_num=2,
            clause_num=1,
            status="pending_review",
            effective_date=date(2026, 9, 1),
            metadata_json={},
        ),
    ]

    summary = _structure_summary(chunks)

    assert summary == {"chunks": 3, "articles": 2, "clauses": 3, "points": 1}


def test_queue_item_warning_count_ignores_hidden_source_url_warning():
    document = LegalDocument(
        doc_id="doc-1",
        title="Thong tu test",
        doc_type="THONG_TU",
        status="pending_review",
        effective_date=date(2026, 9, 1),
        issuer="Bo GTVT",
        domain_tags=[],
    )
    queue = KbUpdateQueue(
        queue_id="queue-1",
        doc_id="doc-1",
        review_status="pending",
        processing_status="ready",
        change_type="create",
        created_at=datetime(2026, 6, 22, 10, 0, 0),
        warning_messages=[
            "Chưa có URL nguồn chính thức; không được approve trước khi bổ sung.",
            "Parser confidence dưới ngưỡng, cần duyệt kỹ.",
        ],
        source_file_name="test.docx",
    )

    item = _queue_item_to_schema(queue, document)

    assert item.warning_count == 1


def test_duplicate_source_detail_keeps_checksum_when_duplicate_payload_missing():
    payload = _duplicate_source_detail("checksum-1", None)

    assert payload["code"] == "DUPLICATE_SOURCE"
    assert payload["source_checksum"] == "checksum-1"
    assert payload["duplicate_document"] is None


def test_queue_source_path_rejects_path_outside_storage(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    raw_dir = tmp_path / "raw"
    upload_dir.mkdir()
    raw_dir.mkdir()
    outside_file = tmp_path / "outside.docx"
    outside_file.write_bytes(b"outside")

    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("src.api.v1.admin_kb._RAW_DIR", raw_dir)

    assert _queue_source_path(str(upload_dir / ".." / "outside.docx")) is None


def test_queue_source_path_accepts_file_inside_storage(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    raw_dir = tmp_path / "raw"
    upload_dir.mkdir()
    raw_dir.mkdir()
    stored_file = upload_dir / "document.docx"
    stored_file.write_bytes(b"inside")

    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("src.api.v1.admin_kb._RAW_DIR", raw_dir)

    assert _queue_source_path(str(stored_file)) == stored_file.resolve()


def test_queue_source_path_ignores_object_storage_uri():
    assert _queue_source_path("s3://legalai/uploads/source.docx") is None


@pytest.mark.asyncio
async def test_save_upload_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", tmp_path)
    upload = UploadFile(filename="payload.exe", file=BytesIO(b"payload"))

    with pytest.raises(HTTPException) as exc_info:
        await _save_upload(upload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "UNSUPPORTED_FILE_TYPE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_file_and_removes_partial_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("src.api.v1.admin_kb.settings.MAX_UPLOAD_FILE_SIZE_MB", 1)
    upload = UploadFile(
        filename="large.pdf",
        file=BytesIO(b"x" * (1024 * 1024 + 1)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await _save_upload(upload)

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["code"] == "FILE_TOO_LARGE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_save_upload_rejects_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", tmp_path)
    upload = UploadFile(filename="empty.docx", file=BytesIO())

    with pytest.raises(HTTPException) as exc_info:
        await _save_upload(upload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "EMPTY_FILE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_kb_document_rejects_invalid_effective_date(client):
    response = await client.post(
        "/api/v1/admin/queue/upload",
        files={
            "file": (
                "test.docx",
                b"fake",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={
            "title": "Thong tu moi",
            "doc_type": "THONG_TU",
            "issuer": "Bo GTVT",
            "effective_date": "not-a-date",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_kb_document_rejects_unsupported_doc_type(client):
    response = await client.post(
        "/api/v1/admin/queue/upload",
        files={
            "file": (
                "test.docx",
                b"fake",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={
            "title": "Thong tu moi",
            "doc_type": "UNKNOWN",
            "issuer": "Bo GTVT",
            "effective_date": "2026-09-01",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_queue_requires_supported_reason(client):
    response = await client.post(
        "/api/v1/admin/queue/queue-1/reject",
        json={"reject_reason": "invalid_reason", "reviewer_note": "Sai metadata"},
    )

    assert response.status_code == 422


class _DuplicateScalarSession:
    def __init__(self, duplicate: LegalDocument | None):
        self.duplicate = duplicate

    async def scalar(self, _statement):
        return self.duplicate


class _DuplicateCandidatesResult:
    def __init__(self, documents):
        self.documents = documents

    def all(self):
        return self.documents


class _DuplicateCandidatesSession:
    def __init__(self, documents):
        self.documents = documents

    async def scalars(self, _statement):
        return _DuplicateCandidatesResult(self.documents)


class _ResolveTargetSession:
    def __init__(
        self,
        *,
        target_document: LegalDocument | None = None,
        pending_queue_id: str | None = None,
        ignore_excluded_pending_queue: bool = False,
    ):
        self.target_document = target_document
        self.pending_queue_id = pending_queue_id
        self.ignore_excluded_pending_queue = ignore_excluded_pending_queue

    async def get(self, _model, _doc_id):
        return self.target_document

    async def scalar(self, statement):
        if self.ignore_excluded_pending_queue and "kb_update_queue.queue_id !=" in str(statement):
            return None
        return self.pending_queue_id


@pytest.mark.asyncio
async def test_upload_kb_document_rejects_exact_duplicate_checksum(client, tmp_path, monkeypatch):
    duplicate = LegalDocument(
        doc_id="dup-1",
        title="Thong tu trung",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 9, 1),
        issuer="Bo GTVT",
        source_url="https://vbpl.test/duplicate",
        domain_tags=[],
    )
    session = _DuplicateScalarSession(duplicate)
    stored_file = tmp_path / "duplicate.docx"
    stored_file.write_bytes(b"same-binary")

    async def override_session():
        yield session

    async def fake_save_upload(_file):
        return SavedUpload(
            safe_name="duplicate.docx",
            local_path=str(stored_file),
            storage_path=str(stored_file),
            checksum="checksum-123",
        )

    monkeypatch.setattr("src.api.v1.admin_kb._save_upload", fake_save_upload)
    monkeypatch.setattr("src.api.v1.admin_kb._UPLOAD_DIR", tmp_path.resolve())
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/queue/upload",
            files={
                "file": (
                    "duplicate.docx",
                    b"fake",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Thong tu moi",
                "doc_type": "THONG_TU",
                "issuer": "Bo GTVT",
                "effective_date": "2026-09-01",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409
    payload = response.json()["detail"]
    assert payload["code"] == "DUPLICATE_SOURCE"
    assert payload["duplicate_document"]["doc_id"] == "dup-1"
    assert Path(stored_file).exists() is False


@pytest.mark.asyncio
async def test_find_duplicate_candidates_matches_source_url_and_metadata():
    documents = [
        LegalDocument(
            doc_id="doc-1",
            title="Thong tu moi",
            doc_type="THONG_TU",
            status="active",
            review_status="approved",
            effective_date=date(2026, 9, 1),
            issuer="Bo GTVT",
            source_url="https://vbpl.test/a",
            domain_tags=[],
        ),
        LegalDocument(
            doc_id="doc-2",
            title="Van ban khac",
            doc_type="THONG_TU",
            status="pending_review",
            review_status="pending",
            effective_date=date(2026, 9, 1),
            issuer="Bo GTVT",
            source_url="https://vbpl.test/b",
            domain_tags=[],
        ),
    ]
    session = _DuplicateCandidatesSession(documents)

    candidates = await _find_duplicate_candidates(
        session,
        title="Thong tu moi",
        doc_type="THONG_TU",
        issuer="Bo GTVT",
        effective_date=date(2026, 9, 1),
        source_url="https://vbpl.test/a",
    )

    assert [candidate["doc_id"] for candidate in candidates] == ["doc-1"]
    assert candidates[0]["reason"] == "source_url,title_issuer_effective_date"


@pytest.mark.asyncio
async def test_resolve_upload_target_document_rejects_target_for_create():
    session = _ResolveTargetSession()

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_upload_target_document(
            session,
            change_type="create",
            target_doc_id="doc-1",
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_upload_target_document_requires_target_for_update():
    session = _ResolveTargetSession()

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_upload_target_document(
            session,
            change_type="update",
            target_doc_id=None,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_resolve_upload_target_document_rejects_missing_target():
    session = _ResolveTargetSession(target_document=None)

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_upload_target_document(
            session,
            change_type="update",
            target_doc_id="missing-doc",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_upload_target_document_rejects_unapproved_target():
    session = _ResolveTargetSession(
        target_document=LegalDocument(
            doc_id="pending-doc",
            title="Ban nhap",
            doc_type="THONG_TU",
            status="pending_review",
            review_status="pending",
            effective_date=date(2026, 9, 1),
            issuer="Bo GTVT",
            domain_tags=[],
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_upload_target_document(
            session,
            change_type="update",
            target_doc_id="pending-doc",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_resolve_upload_target_document_rejects_second_pending_update():
    target_document = LegalDocument(
        doc_id="target-1",
        title="Thong tu dang active",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 9, 1),
        issuer="Bo GTVT",
        domain_tags=[],
    )
    session = _ResolveTargetSession(
        target_document=target_document,
        pending_queue_id="queue-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_upload_target_document(
            session,
            change_type="update",
            target_doc_id="target-1",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_resolve_upload_target_document_allows_current_pending_update_queue():
    target_document = LegalDocument(
        doc_id="target-1",
        title="Thong tu dang active",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 9, 1),
        issuer="Bo GTVT",
        domain_tags=[],
    )
    session = _ResolveTargetSession(
        target_document=target_document,
        pending_queue_id="queue-1",
        ignore_excluded_pending_queue=True,
    )

    resolved = await _resolve_upload_target_document(
        session,
        change_type="update",
        target_doc_id="target-1",
        exclude_queue_id="queue-1",
    )

    assert resolved is target_document


class _ApproveUpdateSession:
    def __init__(self, queue: KbUpdateQueue):
        self.queue = queue
        self.deleted = []
        self.committed = False
        self.scalar_calls = 0

    async def scalar(self, _statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.queue
        return None

    async def get(self, _model, _doc_id):
        return self.queue.target_document

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def _ready_review_queue(
    *,
    warning_messages: list[str] | None = None,
    extracted_metadata: dict | None = None,
) -> KbUpdateQueue:
    document = LegalDocument(
        doc_id="doc-1",
        title="Thong tu test",
        doc_type="THONG_TU",
        status="pending_review",
        review_status="pending",
        effective_date=date(2026, 1, 1),
        issuer="Bo GTVT",
        domain_tags=["road_law"],
    )
    document.chunks = []
    return KbUpdateQueue(
        queue_id="queue-1",
        doc_id="doc-1",
        document=document,
        change_type="create",
        review_status="pending",
        processing_status="ready",
        warning_messages=warning_messages or [],
        extracted_metadata=extracted_metadata or {},
        review_checklist={
            "official_source_verified": True,
            "legal_status_verified": True,
            "source_order_verified": True,
            "corpus_scope_verified": True,
        },
    )


@pytest.mark.asyncio
async def test_approve_clean_queue_allows_empty_reviewer_note(monkeypatch):
    queue = _ready_review_queue()
    session = _ApproveUpdateSession(queue)

    async def fake_detail(_queue_id, _db_session):
        return queue

    monkeypatch.setattr("src.api.v1.admin_kb.get_kb_queue_detail", fake_detail)

    result = await approve_kb_queue_item(
        "queue-1",
        KbQueueApproveRequest(reviewer_note=""),
        session,
    )

    assert result is queue
    assert session.committed is True
    assert queue.review_status == "pending"
    assert queue.processing_status == "queued"
    assert queue.extracted_metadata["approval_job"]["status"] == "running"
    assert queue.extracted_metadata["approval_job"]["step"] == "queued"


@pytest.mark.asyncio
async def test_approve_queue_with_visible_warning_requires_reviewer_note():
    queue = _ready_review_queue(
        warning_messages=["Parser confidence dưới ngưỡng, cần duyệt kỹ."],
    )
    session = _ApproveUpdateSession(queue)

    with pytest.raises(HTTPException) as exc_info:
        await approve_kb_queue_item(
            "queue-1",
            KbQueueApproveRequest(reviewer_note=""),
            session,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "REVIEWER_NOTE_REQUIRED"
    assert session.committed is False


@pytest.mark.asyncio
async def test_approve_queue_with_duplicate_candidates_requires_reviewer_note():
    queue = _ready_review_queue(
        extracted_metadata={"duplicate_candidates": [{"doc_id": "dup-1"}]},
    )
    session = _ApproveUpdateSession(queue)

    with pytest.raises(HTTPException) as exc_info:
        await approve_kb_queue_item(
            "queue-1",
            KbQueueApproveRequest(reviewer_note=None),
            session,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "REVIEWER_NOTE_REQUIRED"
    assert session.committed is False


@pytest.mark.asyncio
async def test_reject_queue_uses_reason_label_when_reviewer_note_empty(monkeypatch):
    queue = _ready_review_queue()
    session = _ApproveUpdateSession(queue)

    async def fake_detail(_queue_id, _db_session):
        return queue

    monkeypatch.setattr("src.api.v1.admin_kb.get_kb_queue_detail", fake_detail)

    result = await reject_kb_queue_item(
        "queue-1",
        KbQueueRejectRequest(reject_reason="metadata_invalid", reviewer_note=None),
        SimpleNamespace(user_id="admin-1"),
        session,
    )

    assert result is queue
    assert session.committed is True
    assert queue.review_status == "rejected"
    assert queue.document.review_status == "rejected"
    assert queue.reject_reason == "metadata_invalid"
    assert queue.reviewer_note == "Thông tin không hợp lệ"


class _SaveDraftSession:
    def __init__(self, queue: KbUpdateQueue):
        self.queue = queue
        self.scalars_called = False
        self.committed = False

    async def scalar(self, _statement):
        return self.queue

    async def scalars(self, _statement):
        self.scalars_called = True
        return _DuplicateCandidatesResult([])

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_metadata_only_draft_unchanged_target_does_not_warn_duplicate(monkeypatch):
    target = LegalDocument(
        doc_id="target-1",
        title="Thong tu cu",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 1, 1),
        expiry_date=None,
        issuer="Bo GTVT",
        source_url="https://vbpl.test/current",
        domain_tags=["road_law"],
    )
    staging = LegalDocument(
        doc_id="staging-1",
        title=target.title,
        doc_type=target.doc_type,
        status="pending_review",
        review_status="pending",
        effective_date=target.effective_date,
        expiry_date=target.expiry_date,
        issuer=target.issuer,
        source_url=target.source_url,
        domain_tags=list(target.domain_tags),
    )
    staging.chunks = []
    queue = KbUpdateQueue(
        queue_id="queue-1",
        doc_id="staging-1",
        target_doc_id="target-1",
        document=staging,
        target_document=target,
        change_type="update",
        review_status="pending",
        processing_status="ready",
        warning_messages=["Phat hien tai lieu co dau hieu trung lap: 1 tai lieu can reviewer doi chieu."],
        extracted_metadata={"metadata_only": True, "duplicate_candidates": [{"doc_id": "target-1"}]},
    )
    session = _SaveDraftSession(queue)

    async def fake_detail(_queue_id, _db_session):
        return queue

    monkeypatch.setattr("src.api.v1.admin_kb.get_kb_queue_detail", fake_detail)

    result = await save_kb_queue_draft(
        "queue-1",
        KbQueueDraftRequest(reviewer_draft_note="Kiem tra metadata"),
        session,
    )

    assert result is queue
    assert session.committed is True
    assert session.scalars_called is False
    assert queue.warning_messages == []
    assert "duplicate_candidates" not in queue.extracted_metadata


@pytest.mark.asyncio
async def test_approve_update_merges_staging_into_target_without_deleting_queue(monkeypatch):
    target = LegalDocument(
        doc_id="target-1",
        title="Thong tu cu",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 1, 1),
        issuer="Bo GTVT",
        domain_tags=["road_law"],
        source_checksum="old-checksum",
        source_version=2,
    )
    old_chunk = DocumentChunk(
        doc_id="target-1",
        text_content="Noi dung cu",
        chunk_type="dieu",
        article_num=1,
        status="active",
        effective_date=date(2026, 1, 1),
        metadata_json={},
        embedding_vector=[0.1, 0.2],
    )
    old_asset = DocumentAsset(
        doc_id="target-1",
        asset_kind="source",
        checksum="old-asset",
        mime_type="application/pdf",
        original_asset_key="old.pdf",
    )
    target.chunks = [old_chunk]
    target.assets = [old_asset]

    staging = LegalDocument(
        doc_id="staging-1",
        title="Thong tu moi",
        doc_type="THONG_TU",
        status="pending_review",
        review_status="pending",
        effective_date=date(2026, 2, 1),
        valid_from=date(2026, 2, 1),
        issuer="Bo GTVT",
        domain_tags=["driver_compliance"],
        source_checksum=None,
    )
    new_chunk = DocumentChunk(
        doc_id="staging-1",
        text_content="Noi dung moi",
        chunk_type="dieu",
        article_num=2,
        status="pending_review",
        effective_date=date(2026, 2, 1),
        metadata_json={},
        embedding_vector=[0.3, 0.4],
    )
    new_asset = DocumentAsset(
        doc_id="staging-1",
        asset_kind="source",
        checksum="new-asset",
        mime_type="application/pdf",
        original_asset_key="new.pdf",
    )
    staging.chunks = [new_chunk]
    staging.assets = [new_asset]

    queue = KbUpdateQueue(
        queue_id="queue-1",
        doc_id="staging-1",
        target_doc_id="target-1",
        document=staging,
        target_document=target,
        change_type="update",
        review_status="pending",
        processing_status="ready",
        extracted_metadata={"source_checksum": "new-checksum"},
        review_checklist={
            "official_source_verified": True,
            "legal_status_verified": True,
            "source_order_verified": True,
            "corpus_scope_verified": True,
        },
    )
    session = _ApproveUpdateSession(queue)

    async def fake_detail(_queue_id, _db_session):
        return queue

    monkeypatch.setattr("src.api.v1.admin_kb.get_kb_queue_detail", fake_detail)

    result = await approve_kb_queue_item(
        "queue-1",
        KbQueueApproveRequest(reviewer_note="Da doi chieu nguon"),
        session,
    )

    assert result is queue
    assert session.committed is True
    assert queue.review_status == "pending"
    assert queue.processing_status == "queued"
    assert queue.extracted_metadata["approval_job"]["status"] == "running"
    assert queue.document is staging
    assert session.deleted == []
    assert old_chunk.document is target
    assert new_chunk.document is staging
    assert target.title == "Thong tu cu"
    assert target.source_checksum == "old-checksum"
    assert target.source_version == 2


@pytest.mark.asyncio
async def test_approve_metadata_only_update_keeps_target_source_and_chunks(monkeypatch):
    target = LegalDocument(
        doc_id="target-1",
        title="Thong tu cu",
        doc_type="THONG_TU",
        status="active",
        review_status="approved",
        effective_date=date(2026, 1, 1),
        issuer="Bo GTVT",
        domain_tags=["road_law"],
        source_checksum="old-checksum",
        source_version=4,
    )
    old_chunk = DocumentChunk(
        doc_id="target-1",
        text_content="Noi dung cu",
        chunk_type="dieu",
        article_num=1,
        status="active",
        effective_date=date(2026, 1, 1),
        metadata_json={},
        embedding_vector=None,
    )
    old_asset = DocumentAsset(
        doc_id="target-1",
        asset_kind="source",
        checksum="old-asset",
        mime_type="application/pdf",
        original_asset_key="old.pdf",
    )
    target.chunks = [old_chunk]
    target.assets = [old_asset]

    staging = LegalDocument(
        doc_id="staging-1",
        title="Thong tu da chinh thong tin",
        doc_type="THONG_TU",
        status="pending_review",
        review_status="pending",
        effective_date=date(2026, 3, 1),
        valid_from=date(2026, 3, 1),
        issuer="Bo Xay dung",
        domain_tags=["transport_business"],
        source_url="https://vbpl.test/new-metadata",
    )
    staging.chunks = []
    staging.assets = []

    queue = KbUpdateQueue(
        queue_id="queue-1",
        doc_id="staging-1",
        target_doc_id="target-1",
        document=staging,
        target_document=target,
        change_type="update",
        review_status="pending",
        processing_status="ready",
        extracted_metadata={"metadata_only": True},
        review_checklist={
            "official_source_verified": True,
            "legal_status_verified": True,
            "source_order_verified": True,
            "corpus_scope_verified": True,
        },
    )
    session = _ApproveUpdateSession(queue)

    async def fake_detail(_queue_id, _db_session):
        return queue

    monkeypatch.setattr("src.api.v1.admin_kb.get_kb_queue_detail", fake_detail)

    result = await approve_kb_queue_item(
        "queue-1",
        KbQueueApproveRequest(reviewer_note="Da doi chieu metadata"),
        session,
    )

    assert result is queue
    assert session.committed is True
    assert queue.review_status == "pending"
    assert queue.processing_status == "queued"
    assert queue.extracted_metadata["approval_job"]["status"] == "running"
    assert queue.document is staging
    assert staging not in session.deleted
    assert old_chunk not in session.deleted
    assert old_asset not in session.deleted
    assert old_chunk.document is target
    assert old_asset.document is target
    assert target.title == "Thong tu cu"
    assert target.issuer == "Bo GTVT"
    assert target.domain_tags == ["road_law"]
    assert target.source_checksum == "old-checksum"
    assert target.source_version == 4
