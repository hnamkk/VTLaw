from __future__ import annotations

from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from sqlalchemy.exc import MissingGreenlet

from src.api.v1.admin_legal_kb import _document_answerable_status
from src.auth.dependencies import require_admin
from src.db.session import get_session
from src.main import app
from src.models.legal_kb import (
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbRetrievalUnit,
    LegalKbReviewEvent,
    LegalKbRevision,
    LegalKbSourceAsset,
    LegalKbSummary,
)


def test_document_status_treats_expiry_as_exclusive():
    document = SimpleNamespace(
        legal_status="active", effective_date=None, expiry_date=date.today()
    )

    assert _document_answerable_status(document) == "historical"


@pytest.fixture(autouse=True)
def admin_dependency_override():
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        user_id="11111111-1111-1111-1111-111111111111",
        role="ADMIN",
        is_active=True,
    )
    yield
    app.dependency_overrides.pop(require_admin, None)


class _LegalKbSession:
    def __init__(self, *, duplicate: LegalKbSourceAsset | None = None):
        self.duplicate = duplicate
        self.added: list[object] = []
        self.committed = False

    async def scalar(self, _statement):
        return self.duplicate

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True


class _ReplacementUploadSession(_LegalKbSession):
    def __init__(self, document: LegalKbDocument):
        super().__init__()
        self.scalars = [document, None]

    async def scalar(self, _statement):
        if not self.scalars:
            raise AssertionError("Unexpected scalar call")
        return self.scalars.pop(0)


class _ListResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def all(self):
        return self.rows


class _SequenceSession:
    def __init__(self, *results):
        self.results = list(results)

    async def execute(self, _statement):
        if not self.results:
            raise AssertionError("Unexpected execute call")
        return self.results.pop(0)


class _ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def unique(self):
        return self.rows

    def all(self):
        return self.rows


class _DocumentListResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _ScalarResult(self.rows)


def _build_docx_bytes() -> bytes:
    buffer = BytesIO()
    document = Document()
    document.add_paragraph("Điều 1. Quy định chung")
    document.add_paragraph("Văn bản này áp dụng cho tuyến thử nghiệm.")
    document.add_paragraph("1. Người lái xe phải mang theo giấy tờ hợp lệ.")
    document.add_paragraph("a) Bản chính giấy phép lái xe.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Mục"
    table.rows[0].cells[1].text = "Giá trị"
    table.rows[1].cells[0].text = "Tốc độ"
    table.rows[1].cells[1].text = "80 km/h"
    document.save(buffer)
    return buffer.getvalue()


def _build_docx_with_review_only_blocks() -> bytes:
    buffer = BytesIO()
    document = Document()
    header = document.add_table(rows=2, cols=2)
    header.rows[0].cells[0].text = "QUOC HOI"
    header.rows[0].cells[1].text = "CONG HOA XA HOI CHU NGHIA VIET NAM"
    header.rows[1].cells[0].text = "Luat so: 35/2024/QH15"
    header.rows[1].cells[1].text = "Ha Noi, ngay 27 thang 6 nam 2024"
    document.add_paragraph("LUAT")
    document.add_paragraph("DUONG BO")
    document.add_paragraph("Dieu 1. Pham vi dieu chinh")
    document.add_paragraph("Luat nay quy dinh ve hoat dong duong bo va quan ly nha nuoc ve hoat dong duong bo.")
    signature = document.add_table(rows=1, cols=1)
    signature.rows[0].cells[0].text = "CHU TICH QUOC HOI\nTran Thanh Man"
    document.add_paragraph("Noi nhan: Uy ban Thuong vu Quoc hoi; Chinh phu.")
    document.save(buffer)
    return buffer.getvalue()


def _build_docx_with_appendix_and_footnotes() -> bytes:
    buffer = BytesIO()
    document = Document()
    document.add_paragraph("Điều 1. Quy định chung")
    document.add_paragraph("1. Người lái xe phải tuân thủ biển báo và hiệu lệnh.")
    article_table = document.add_table(rows=2, cols=2)
    article_table.rows[0].cells[0].text = "Hành vi"
    article_table.rows[0].cells[1].text = "Mức phạt"
    article_table.rows[1].cells[0].text = "Vượt đèn đỏ"
    article_table.rows[1].cells[1].text = "Theo quy định hiện hành"
    document.add_paragraph("Phụ lục I")
    document.add_paragraph("Mẫu số 01 - Đơn đề nghị")
    appendix_table = document.add_table(rows=2, cols=2)
    appendix_table.rows[0].cells[0].text = "Cột A"
    appendix_table.rows[0].cells[1].text = "Cột B"
    appendix_table.rows[1].cells[0].text = "Dữ liệu"
    appendix_table.rows[1].cells[1].text = "Mẫu"
    document.add_paragraph("[1] Nguồn: Bản sao phục vụ tra cứu.")
    document.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_legal_kb_upload_endpoint_available_without_feature_flag(client, monkeypatch, tmp_path):
    from src.core.config import settings

    monkeypatch.setattr(settings, "KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "OBJECT_STORAGE_ENABLED", False)
    monkeypatch.setattr(settings, "KB_REQUIRE_OBJECT_STORAGE", False)
    session = _LegalKbSession()

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/revisions/upload",
            files={"file": ("fresh.docx", _build_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={
                "title": "Thông tư thử nghiệm kho văn bản",
                "source_url": "https://example.test/fresh.docx",
                "source_downloaded_at": "2026-07-02",
                "source_note": "Nguồn thử nghiệm",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_legal_kb_upload_creates_draft_revision_and_canonical_nodes(client, tmp_path, monkeypatch):
    session = _LegalKbSession()

    async def override_session():
        yield session

    monkeypatch.setattr("src.legal_kb.ingestion.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr("src.legal_kb.ingestion.settings.OBJECT_STORAGE_ENABLED", False)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/revisions/upload",
            files={
                "file": (
                    "fresh.docx",
                    _build_docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Thông tư thử nghiệm kho văn bản",
                "document_number": "12/2026/TT-BGTVT",
                "document_type": "THONG_TU",
                "issuing_authority": "Bộ GTVT",
                "issued_date": "2026-07-01",
                "effective_date": "2026-08-01",
                "source_url": "https://example.test/fresh.docx",
                "source_downloaded_at": "2026-07-02",
                "source_note": "Tải mới từ nguồn thử nghiệm",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["revision"]["publication_status"] == "draft"
    assert payload["revision"]["review_status"] == "needs_review"
    assert payload["revision"]["ingestion_status"] == "parsed"
    assert payload["source_asset"]["original_filename"] == "fresh.docx"
    assert payload["source_asset"]["source_downloaded_at"] == "2026-07-02"
    assert any(node["node_type"] == "article" for node in payload["canonical_nodes"])
    assert any(node["node_type"] == "clause" for node in payload["canonical_nodes"])
    assert any(node["node_type"] == "table" for node in payload["canonical_nodes"])
    assert any(
        node["node_type"] == "table"
        and node["review_status"] == "approved"
        and node["structured_content"].get("answerable") is True
        for node in payload["canonical_nodes"]
    )
    assert any(node["node_type"] == "article" and node["review_status"] == "approved" for node in payload["canonical_nodes"])

    documents = [obj for obj in session.added if isinstance(obj, LegalKbDocument)]
    revisions = [obj for obj in session.added if isinstance(obj, LegalKbRevision)]
    source_assets = [obj for obj in session.added if isinstance(obj, LegalKbSourceAsset)]
    metadata_proposals = [obj for obj in session.added if isinstance(obj, LegalKbMetadataProposal)]
    summaries = [obj for obj in session.added if isinstance(obj, LegalKbSummary)]
    retrieval_units = [obj for obj in session.added if isinstance(obj, LegalKbRetrievalUnit)]

    assert len(documents) == 1
    assert len(revisions) == 1
    assert len(source_assets) == 1
    assert any(proposal.field_name == "document_role" for proposal in metadata_proposals)
    assert any(proposal.field_name == "effective_date" for proposal in metadata_proposals)
    assert all(proposal.review_status == "approved" for proposal in metadata_proposals)
    assert len(summaries) == 1
    assert summaries[0].review_status == "needs_review"
    assert summaries[0].content.startswith("Tóm tắt chuẩn")
    assert "Thông tin pháp lý" in summaries[0].content
    assert "Phạm vi / đối tượng áp dụng" in summaries[0].content
    assert "Nội dung chính" in summaries[0].content
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" not in summaries[0].content
    assert retrieval_units == []
    assert session.committed is True
    assert revisions[0].source_downloaded_at == date(2026, 7, 2)


@pytest.mark.asyncio
async def test_legal_kb_replacement_upload_creates_draft_revision_for_existing_document(client, tmp_path, monkeypatch):
    document = LegalKbDocument(
        document_id="22222222-2222-2222-2222-222222222222",
        title="Nghị định đang công bố",
        document_number="67/2023/NĐ-CP",
        document_type="NGHI_DINH",
        issuing_authority="Chính phủ",
        issued_date=date(2023, 9, 6),
        effective_date=date(2023, 9, 6),
        legal_status="active",
        metadata_json={"document_role": "base"},
    )
    document.revisions = [
        LegalKbRevision(
            revision_id="33333333-3333-3333-3333-333333333333",
            document_id=document.document_id,
            revision_number=1,
            ingestion_status="parsed",
            review_status="approved",
            publication_status="published",
            uploaded_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
    ]
    session = _ReplacementUploadSession(document)

    async def override_session():
        yield session

    monkeypatch.setattr("src.legal_kb.ingestion.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr("src.legal_kb.ingestion.settings.OBJECT_STORAGE_ENABLED", False)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            f"/api/v1/admin/legal-kb/documents/{document.document_id}/replacement-revisions/upload",
            files={
                "file": (
                    "replacement.docx",
                    _build_docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Nghị định đang công bố - bản đối chiếu mới",
                "document_number": "67/2023/NĐ-CP",
                "document_type": "NGHI_DINH",
                "document_role": "base",
                "issuing_authority": "Chính phủ",
                "issued_date": "2023-09-06",
                "effective_date": "2023-09-06",
                "source_url": "https://example.test/replacement.docx",
                "source_downloaded_at": "2026-07-08",
                "source_note": "Thay file nguồn sau đối chiếu.",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201
    payload = response.json()
    assert payload["document"]["document_id"] == document.document_id
    assert payload["revision"]["document_id"] == document.document_id
    assert payload["revision"]["revision_number"] == 2
    assert payload["revision"]["publication_status"] == "draft"
    assert payload["source_asset"]["original_filename"] == "replacement.docx"

    documents = [obj for obj in session.added if isinstance(obj, LegalKbDocument)]
    revisions = [obj for obj in session.added if isinstance(obj, LegalKbRevision)]
    events = [obj for obj in session.added if isinstance(obj, LegalKbReviewEvent)]

    assert documents == []
    assert len(revisions) == 1
    assert revisions[0].document_id == document.document_id
    assert any(event.details.get("upload_mode") == "replacement" for event in events)
    assert session.committed is True


@pytest.mark.asyncio
async def test_legal_kb_upload_marks_header_signature_and_distribution_as_review_only(client, tmp_path, monkeypatch):
    session = _LegalKbSession()

    async def override_session():
        yield session

    monkeypatch.setattr("src.legal_kb.ingestion.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr("src.legal_kb.ingestion.settings.OBJECT_STORAGE_ENABLED", False)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/revisions/upload",
            files={
                "file": (
                    "review-only.docx",
                    _build_docx_with_review_only_blocks(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Luat Duong bo",
                "document_number": "35/2024/QH15",
                "document_type": "LUAT",
                "issuing_authority": "Quoc hoi",
                "issued_date": "2024-06-27",
                "effective_date": "2025-01-01",
                "source_url": "https://example.test/review-only.docx",
                "source_downloaded_at": "2026-07-02",
                "source_note": "Nguon thu nghiem review-only",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201
    payload = response.json()
    roles = {
        node["structured_content"].get("review_only_role"): node
        for node in payload["canonical_nodes"]
        if node["structured_content"].get("review_only_role")
    }
    assert roles["national_header"]["review_status"] == "approved"
    assert roles["signature_block"]["review_status"] == "approved"
    assert roles["distribution_list"]["review_status"] == "approved"
    assert roles["national_header"]["structured_content"]["review_only"] is True
    assert roles["national_header"]["structured_content"]["answerable"] is False

    summaries = [obj for obj in session.added if isinstance(obj, LegalKbSummary)]
    assert len(summaries) == 1
    assert "quốc hiệu, tiêu ngữ" in summaries[0].content.lower()


@pytest.mark.asyncio
async def test_legal_kb_upload_auto_classifies_article_tables_appendix_materials_and_footnotes(client, tmp_path, monkeypatch):
    session = _LegalKbSession()

    async def override_session():
        yield session

    monkeypatch.setattr("src.legal_kb.ingestion.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr("src.legal_kb.ingestion.settings.OBJECT_STORAGE_ENABLED", False)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/revisions/upload",
            files={
                "file": (
                    "appendix.docx",
                    _build_docx_with_appendix_and_footnotes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Nghi dinh thu nghiem",
                "document_number": "67/2023/ND-CP",
                "document_type": "NGHI_DINH",
                "issuing_authority": "Chinh phu",
                "issued_date": "2023-09-06",
                "effective_date": "2023-09-06",
                "source_url": "https://example.test/appendix.docx",
                "source_downloaded_at": "2026-07-04",
                "source_note": "Nguon thu nghiem appendix",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 201
    nodes = response.json()["canonical_nodes"]
    article_table = next(
        node
        for node in nodes
        if node["node_type"] == "table" and node["structured_content"].get("in_appendix") is False
    )
    appendix_heading = next(node for node in nodes if node["node_type"] == "appendix")
    appendix_table = next(
        node
        for node in nodes
        if node["node_type"] == "table" and node["structured_content"].get("in_appendix") is True
    )
    footnote = next(
        node
        for node in nodes
        if node["structured_content"].get("review_only_role") == "citation_note"
    )

    assert article_table["review_status"] == "approved"
    assert article_table["structured_content"]["answerable"] is True
    assert article_table["structured_content"]["container_type"] == "clause"
    assert appendix_heading["review_status"] == "approved"
    assert appendix_table["review_status"] == "approved"
    assert appendix_table["parent_id"] == appendix_heading["node_id"]
    assert appendix_table["structured_content"]["review_only"] is True
    assert appendix_table["structured_content"]["review_only_role"] == "appendix_material"
    assert appendix_table["structured_content"]["answerable"] is False
    assert footnote["review_status"] == "approved"
    assert footnote["structured_content"]["review_only"] is True
    assert footnote["structured_content"]["answerable"] is False


@pytest.mark.asyncio
async def test_legal_kb_upload_rejects_duplicate_checksum(client, tmp_path, monkeypatch):
    session = _LegalKbSession(
        duplicate=LegalKbSourceAsset(
            asset_id="asset-1",
            document_id="doc-1",
            revision_id="rev-1",
            asset_role="source",
            storage_uri="s3://legalai/legal-kb/sources/doc-1/rev-1/file.docx",
            original_filename="existing.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256="ignored",
        )
    )

    async def override_session():
        yield session

    monkeypatch.setattr("src.legal_kb.ingestion.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr("src.legal_kb.ingestion.settings.OBJECT_STORAGE_ENABLED", False)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/revisions/upload",
            files={
                "file": (
                    "fresh.docx",
                    _build_docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "title": "Thông tư thử nghiệm kho văn bản",
                "source_url": "https://example.test/fresh.docx",
                "source_downloaded_at": "2026-07-02",
                "source_note": "Nguồn thử nghiệm",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "KB_DUPLICATE_SOURCE"
    assert response.json()["detail"]["document_id"] == "doc-1"
    assert response.json()["detail"]["revision_id"] == "rev-1"
    assert session.committed is False


@pytest.mark.asyncio
async def test_legal_kb_revision_list_returns_revision_rows(client, monkeypatch):
    session = _SequenceSession(
        _ListResult(scalar_value=1),
        _ListResult(
            rows=[
                (
                    SimpleNamespace(
                        revision_id="rev-v2",
                        document_id="doc-v2",
                        review_status="approved",
                        publication_status="published",
                        ingestion_status="parsed",
                        created_at=datetime(2026, 7, 2, tzinfo=UTC),
                        uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
                        source_asset=SimpleNamespace(sha256="abc123", metadata_json={}),
                        metadata_proposals=[
                            SimpleNamespace(review_status="approved"),
                            SimpleNamespace(review_status="needs_review"),
                        ],
                        standard_summaries=[
                            SimpleNamespace(revision_id="rev-v2", review_status="approved"),
                        ],
                        canonical_nodes=[
                            SimpleNamespace(
                                node_type="table",
                                review_status="needs_review",
                                structured_content={},
                            ),
                            SimpleNamespace(
                                node_type="clause",
                                review_status="approved",
                                structured_content={},
                            ),
                        ],
                        review_events=[
                            SimpleNamespace(decision="metadata_reviewed", created_at=datetime(2026, 7, 5, tzinfo=UTC)),
                        ],
                        document=SimpleNamespace(
                            title="Van ban kho văn bản",
                            document_number="12/2026/TT-BGTVT",
                            document_type="THONG_TU",
                            issuing_authority="Bo GTVT",
                            effective_date=date(2026, 8, 1),
                            expiry_date=None,
                            legal_status="active",
                            document_id="doc-v2",
                            outgoing_relations=[
                                SimpleNamespace(
                                    relation_id="rel-out",
                                    source_document_id="doc-v2",
                                    target_document_id="doc-other",
                                    relation_type="amends",
                                    metadata_json={"review_status": "approved"},
                                    created_at=datetime(2026, 7, 3, tzinfo=UTC),
                                )
                            ],
                            incoming_relations=[
                                SimpleNamespace(
                                    relation_id="rel-in",
                                    source_document_id="doc-older",
                                    target_document_id="doc-v2",
                                    relation_type="guides",
                                    metadata_json={"review_status": "needs_review"},
                                    created_at=datetime(2026, 7, 4, tzinfo=UTC),
                                )
                            ],
                        ),
                    ),
                    "fresh.docx",
                )
            ]
        ),
    )

    async def override_session():
        yield session

    monkeypatch.setattr("src.api.v1.admin_legal_kb.collect_publish_blockers", lambda _bundle: ["node pending"])
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/revisions")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["revision_id"] == "rev-v2"
    assert payload["items"][0]["source_file_name"] == "fresh.docx"
    assert payload["items"][0]["issuing_authority"] == "Bo GTVT"
    assert payload["items"][0]["effective_date"] == "2026-08-01"
    assert payload["items"][0]["expiry_date"] is None
    assert payload["items"][0]["pending_metadata_count"] == 1
    assert payload["items"][0]["pending_relations_count"] == 0
    assert payload["items"][0]["pending_risky_nodes_count"] == 1
    assert payload["items"][0]["summary_status"] == "approved"
    assert payload["items"][0]["publish_blockers_count"] == 1
    assert payload["items"][0]["is_ready_to_publish"] is False
    assert payload["items"][0]["relation_count"] == 2
    assert payload["items"][0]["updated_at"] == "2026-07-05T00:00:00Z"


@pytest.mark.asyncio
async def test_legal_kb_revision_list_leaves_updated_at_empty_when_only_created_event_exists(client, monkeypatch):
    session = _SequenceSession(
        _ListResult(scalar_value=1),
        _ListResult(
            rows=[
                (
                    SimpleNamespace(
                        revision_id="rev-created-only",
                        document_id="doc-created-only",
                        review_status="needs_review",
                        publication_status="draft",
                        ingestion_status="parsed",
                        created_at=datetime(2026, 7, 2, tzinfo=UTC),
                        uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
                        source_asset=SimpleNamespace(sha256="abc123", metadata_json={}),
                        metadata_proposals=[],
                        standard_summaries=[],
                        canonical_nodes=[],
                        review_events=[
                            SimpleNamespace(decision="created", created_at=datetime(2026, 7, 2, tzinfo=UTC)),
                        ],
                        document=SimpleNamespace(
                            title="Ho so moi tao",
                            document_number="01/2026/HS",
                            document_type="THONG_TU",
                            issuing_authority="Bo GTVT",
                            effective_date=None,
                            expiry_date=None,
                            legal_status="draft",
                            metadata_json={},
                            document_id="doc-created-only",
                            outgoing_relations=[],
                            incoming_relations=[],
                        ),
                    ),
                    "created-only.docx",
                )
            ]
        ),
    )

    async def override_session():
        yield session

    monkeypatch.setattr("src.api.v1.admin_legal_kb.collect_publish_blockers", lambda _bundle: [])
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/revisions")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["uploaded_at"] == "2026-07-02T00:00:00Z"
    assert payload["items"][0]["updated_at"] is None


@pytest.mark.asyncio
async def test_legal_kb_revision_list_returns_friendly_error_when_serialization_fails(client, monkeypatch):
    session = _SequenceSession(
        _ListResult(scalar_value=1),
        _ListResult(
            rows=[
                (
                    SimpleNamespace(
                        revision_id="rev-broken",
                        document_id="doc-broken",
                        review_status="needs_review",
                        publication_status="draft",
                        ingestion_status="parsed",
                        created_at=datetime(2026, 7, 2, tzinfo=UTC),
                        uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
                        source_asset=None,
                        metadata_proposals=[],
                        standard_summaries=[],
                        canonical_nodes=[],
                        review_events=[],
                        document=SimpleNamespace(
                            title="Ho so loi",
                            document_number="01/2026/ERR",
                            document_type="THONG_TU",
                            issuing_authority="Bo GTVT",
                            effective_date=None,
                            expiry_date=None,
                            legal_status="draft",
                            metadata_json={},
                            document_id="doc-broken",
                            outgoing_relations=[],
                            incoming_relations=[],
                        ),
                    ),
                    "broken.docx",
                )
            ]
        ),
    )

    async def override_session():
        yield session

    def raise_unexpected(*, revision, source_file_name):
        raise RuntimeError(f"broken revision: {revision.revision_id} / {source_file_name}")

    monkeypatch.setattr("src.api.v1.admin_legal_kb._serialize_revision_list_item", raise_unexpected)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/revisions")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "KB_DOCUMENT_LIST_UNAVAILABLE"
    assert "danh sách" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_legal_kb_published_document_list_serializes_revision_summary_source_and_relations(client, monkeypatch):
    revision = SimpleNamespace(
        revision_id="rev-v2",
        publication_status="published",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
        source_asset=SimpleNamespace(original_filename="fresh.docx"),
        standard_summaries=[
            SimpleNamespace(
                summary_id="summary-v2",
                revision_id="rev-v2",
                content="Tóm tắt chuẩn",
                review_status="approved",
                approved_by="admin-user",
                approved_at=datetime(2026, 7, 2, tzinfo=UTC),
            )
        ],
    )
    document = SimpleNamespace(
        document_id="doc-v2",
        title="Văn bản đang công bố",
        document_number="12/2026/TT-BGTVT",
        document_type="THONG_TU",
        issuing_authority="Bộ GTVT",
        effective_date=date(2026, 8, 1),
        expiry_date=None,
        legal_status="active",
        metadata_json={},
        updated_at=datetime(2026, 7, 3, tzinfo=UTC),
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        revisions=[revision],
        source_assets=[],
        outgoing_relations=[
            SimpleNamespace(
                relation_id="rel-out",
                source_document_id="doc-v2",
                target_document_id="doc-other",
                relation_type="amends",
                created_at=datetime(2026, 7, 3, tzinfo=UTC),
            )
        ],
        incoming_relations=[
            SimpleNamespace(
                relation_id="rel-in",
                source_document_id="doc-previous",
                target_document_id="doc-v2",
                relation_type="replaced_by",
                created_at=datetime(2026, 7, 4, tzinfo=UTC),
            )
        ],
    )
    session = _SequenceSession(_DocumentListResult([document]))

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/documents?page=1&page_size=10")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["document_id"] == "doc-v2"
    assert payload["items"][0]["revision_id"] == "rev-v2"
    assert payload["items"][0]["source_file_name"] == "fresh.docx"
    assert payload["items"][0]["relation_count"] == 2
    assert payload["items"][0]["display_status"] == "active"


@pytest.mark.asyncio
async def test_legal_kb_relation_targets_include_draft_documents_and_exclude_current_document(client):
    documents = [
        SimpleNamespace(
            document_id="doc-draft",
            document_number="151/2024/ND-CP",
            title="Van ban dang xu ly",
        ),
        SimpleNamespace(
            document_id="doc-published",
            document_number="168/2024/ND-CP",
            title="Van ban da dua vao kho",
        ),
    ]
    session = _SequenceSession(
        _ListResult(scalar_value=2),
        _DocumentListResult(documents),
    )

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get(
            "/api/v1/admin/legal-kb/relation-targets",
            params={"q": "2024", "exclude_document_id": "doc-current"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "document_id": "doc-draft",
                "document_number": "151/2024/ND-CP",
                "title": "Van ban dang xu ly",
            },
            {
                "document_id": "doc-published",
                "document_number": "168/2024/ND-CP",
                "title": "Van ban da dua vao kho",
            },
        ],
        "total": 2,
    }


@pytest.mark.asyncio
async def test_legal_kb_published_document_list_hides_internal_server_error_when_serialization_fails(client, monkeypatch):
    document = SimpleNamespace(
        document_id="doc-v2",
        title="Văn bản đang công bố",
        document_number="12/2026/TT-BGTVT",
        document_type="THONG_TU",
        issuing_authority="Bộ GTVT",
        effective_date=date(2026, 8, 1),
        expiry_date=None,
        legal_status="active",
        metadata_json={},
        updated_at=datetime(2026, 7, 3, tzinfo=UTC),
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        revisions=[],
        source_assets=[],
        outgoing_relations=[],
        incoming_relations=[],
    )
    session = _SequenceSession(_DocumentListResult([document]))

    async def override_session():
        yield session

    def raise_missing_greenlet(_document):
        raise MissingGreenlet("greenlet_spawn has not been called")

    monkeypatch.setattr("src.api.v1.admin_legal_kb._managed_bundle_from_document", raise_missing_greenlet)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/documents?page=1&page_size=10")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "KB_INTERNAL_ERROR"
    assert "Internal Server Error" not in response.text
    assert response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_legal_kb_revision_detail_returns_review_aggregate_fields(client, monkeypatch):
    session = _LegalKbSession()

    async def override_session():
        yield session

    def node(node_id: str, *, node_type: str, review_status: str, structured_content: dict):
        return SimpleNamespace(
            node_id=node_id,
            revision_id="rev-v2",
            parent_id=None,
            node_type=node_type,
            label=node_id,
            text=node_id,
            order_index=1,
            review_status=review_status,
            provenance={},
            structured_content=structured_content,
        )

    async def fake_load_revision_bundle(_session, revision_id: str):
        assert revision_id == "rev-v2"
        revision = SimpleNamespace(
            revision_id="rev-v2",
            document_id="doc-v2",
            revision_number=1,
            ingestion_status="parsed",
            review_status="needs_review",
            publication_status="draft",
            checksum_sha256="abc",
            source_url="https://example.test/docx",
            source_downloaded_at=date(2026, 7, 2),
            source_note="note",
            parser_version="test",
            uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
            canonical_nodes=[
                node("pending-table", node_type="table", review_status="needs_review", structured_content={}),
                node("answerable-table", node_type="table", review_status="approved", structured_content={"answerable": True}),
                node("reference-appendix", node_type="appendix", review_status="approved", structured_content={"review_only": True}),
            ],
            metadata_proposals=[
                SimpleNamespace(
                    proposal_id="meta-pending",
                    document_id="doc-v2",
                    revision_id="rev-v2",
                    field_name="document_type",
                    proposed_value="NGHI_DINH",
                    source_type="parser",
                    confidence=0.9,
                    review_status="needs_review",
                    provenance={},
                    review_note=None,
                    reviewed_by=None,
                    reviewed_at=None,
                    created_at=datetime(2026, 7, 2, tzinfo=UTC),
                )
            ],
            retrieval_units=[],
            review_events=[],
            standard_summaries=[],
        )
        return SimpleNamespace(
            document=SimpleNamespace(
                document_id="doc-v2",
                title="Van ban kho văn bản",
                document_number="12/2026/TT-BGTVT",
                document_type="THONG_TU",
                issuing_authority="Bo GTVT",
                issued_date=date(2026, 7, 1),
                effective_date=date(2026, 8, 1),
                expiry_date=None,
                legal_status="active",
                metadata_json={},
            ),
            revision=revision,
            source_asset=None,
            relations=[
                SimpleNamespace(
                    relation_id="rel-pending",
                    source_document_id="doc-v2",
                    target_document_id="doc-target",
                    relation_type="depends_on",
                    source_locator=None,
                    target_locator=None,
                    metadata_json={"review_status": "needs_review"},
                    created_at=datetime(2026, 7, 2, tzinfo=UTC),
                )
            ],
            summary=SimpleNamespace(
                summary_id="summary-v2",
                document_id="doc-v2",
                revision_id="rev-v2",
                content="Tom tat",
                review_status="approved",
                approved_by="admin",
                approved_at=datetime(2026, 7, 2, tzinfo=UTC),
            ),
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.normalize_legacy_revision_review_state", lambda _bundle: False)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.collect_publish_blockers", lambda _bundle: [])
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/revisions/rev-v2")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert [item["node_id"] for item in payload["pending_risky_nodes"]] == ["pending-table"]
    assert {item["node_id"] for item in payload["resolved_risky_nodes"]} == {"answerable-table", "reference-appendix"}
    assert payload["resolved_risky_count"] == 2
    assert payload["risky_answerable_count"] == 1
    assert payload["risky_reference_only_count"] == 1
    assert payload["pending_metadata"][0]["proposal_id"] == "meta-pending"
    assert payload["pending_relations"][0]["relation_id"] == "rel-pending"
    assert payload["is_ready_to_publish"] is True


@pytest.mark.asyncio
async def test_legal_kb_revision_detail_returns_friendly_error_when_serialization_fails(client, monkeypatch):
    session = _LegalKbSession()

    async def override_session():
        yield session

    async def fake_load_revision_bundle(_session, revision_id: str):
        assert revision_id == "rev-v2"
        return SimpleNamespace(
            document=SimpleNamespace(document_id="doc-v2"),
            revision=SimpleNamespace(revision_id="rev-v2"),
            source_asset=None,
            relations=[],
            summary=None,
        )

    def raise_unexpected(_bundle):
        raise RuntimeError("broken revision detail")

    monkeypatch.setattr("src.api.v1.admin_legal_kb.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.normalize_legacy_revision_review_state", lambda _bundle: False)
    monkeypatch.setattr("src.api.v1.admin_legal_kb._serialize_revision_detail", raise_unexpected)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get("/api/v1/admin/legal-kb/revisions/rev-v2")
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "KB_REVISION_DETAIL_UNAVAILABLE"
    assert "Internal Server Error" not in response.text
    assert response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_legal_kb_unsuspend_endpoint_calls_publication_service(client, monkeypatch):
    calls: list[tuple[str, str | None]] = []

    async def fake_unsuspend_revision(_session, *, revision_id: str, actor_user_id: str | None):
        calls.append((revision_id, actor_user_id))
        return SimpleNamespace(revision_id=revision_id)

    async def fake_load_revision_bundle(_session, revision_id: str):
        assert revision_id == "rev-v2"
        return SimpleNamespace(
            document=SimpleNamespace(
                document_id="doc-v2",
                title="Van ban kho văn bản",
                document_number="12/2026/TT-BGTVT",
                document_type="THONG_TU",
                issuing_authority="Bo GTVT",
                issued_date=date(2026, 7, 1),
                effective_date=date(2026, 8, 1),
                expiry_date=None,
                legal_status="active",
            ),
            revision=SimpleNamespace(
                revision_id="rev-v2",
                document_id="doc-v2",
                revision_number=1,
                ingestion_status="parsed",
                review_status="approved",
                publication_status="published",
                checksum_sha256="abc",
                source_url="https://example.test/docx",
                source_downloaded_at=date(2026, 7, 2),
                source_note="note",
                parser_version="test",
                uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
                canonical_nodes=[],
                metadata_proposals=[],
                retrieval_units=[],
                review_events=[],
                standard_summaries=[],
            ),
            source_asset=SimpleNamespace(
                asset_id="asset-v2",
                document_id="doc-v2",
                revision_id="rev-v2",
                asset_role="source",
                storage_uri="file:///tmp/fresh.docx",
                original_filename="fresh.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                sha256="abc",
                file_size_bytes=10,
                source_url="https://example.test/docx",
                source_downloaded_at=date(2026, 7, 2),
                source_note="note",
            ),
            relations=[],
            summary=None,
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.unsuspend_revision", fake_unsuspend_revision)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.collect_publish_blockers", lambda _bundle: [])

    response = await client.post("/api/v1/admin/legal-kb/revisions/rev-v2/unsuspend")

    assert response.status_code == 200
    assert calls == [("rev-v2", "11111111-1111-1111-1111-111111111111")]
    assert response.json()["revision"]["revision_id"] == "rev-v2"


@pytest.mark.asyncio
async def test_legal_kb_relation_update_endpoint_calls_review_service(client, monkeypatch):
    calls: list[dict[str, str | None]] = []

    async def fake_update_relation_proposal(_session, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            relation_id="rel-v2",
            source_document_id="source-doc",
            target_document_id=kwargs["target_document_id"],
            relation_type=kwargs["relation_type"],
            source_locator=kwargs["source_locator"],
            target_locator=kwargs["target_locator"],
            metadata_json={"review_status": "needs_review", "note": kwargs["note"]},
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.update_relation_proposal", fake_update_relation_proposal)

    response = await client.patch(
        "/api/v1/admin/legal-kb/relations/rel-v2",
        json={
            "target_document_id": "target-doc",
            "relation_type": "amends",
            "source_locator": "Điều 2",
            "target_locator": "Điều 86",
            "note": "Sửa target/locator trước khi duyệt",
        },
    )

    assert response.status_code == 200
    assert response.json()["relation_type"] == "amends"
    assert response.json()["target_document_id"] == "target-doc"
    assert calls == [
        {
            "relation_id": "rel-v2",
            "actor_user_id": "11111111-1111-1111-1111-111111111111",
            "target_document_id": "target-doc",
            "relation_type": "amends",
            "source_locator": "Điều 2",
            "target_locator": "Điều 86",
            "note": "Sửa target/locator trước khi duyệt",
        }
    ]


@pytest.mark.asyncio
async def test_create_relation_rejects_self_reference(monkeypatch):
    from fastapi import HTTPException

    from src.legal_kb import review as review_service

    document = SimpleNamespace(document_id="doc-v2", outgoing_relations=[])
    bundle = SimpleNamespace(document=document)

    async def fake_load_revision_bundle(_session, _revision_id):
        return bundle

    class Session:
        async def get(self, _model, _document_id):
            return document

    monkeypatch.setattr(review_service, "load_revision_bundle", fake_load_revision_bundle)
    with pytest.raises(HTTPException) as exc_info:
        await review_service.create_relation_proposal(
            Session(),
            revision_id="rev-v2",
            target_document_id="doc-v2",
            relation_type="amends",
            actor_user_id="admin-v2",
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_legal_kb_relation_delete_endpoint_calls_review_service(client, monkeypatch):
    calls = []

    async def fake_delete_relation(_session, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("src.api.v1.admin_legal_kb.delete_relation", fake_delete_relation)
    response = await client.delete("/api/v1/admin/legal-kb/relations/rel-v2")

    assert response.status_code == 204
    assert calls == [
        {
            "relation_id": "rel-v2",
            "actor_user_id": "11111111-1111-1111-1111-111111111111",
        }
    ]


@pytest.mark.asyncio
async def test_create_relation_rejects_duplicate(monkeypatch):
    from fastapi import HTTPException

    from src.legal_kb import review as review_service

    target = SimpleNamespace(document_id="doc-target")
    document = SimpleNamespace(
        document_id="doc-v2",
        outgoing_relations=[SimpleNamespace(target_document_id="doc-target", relation_type="amends")],
    )
    bundle = SimpleNamespace(document=document)

    async def fake_load_revision_bundle(_session, _revision_id):
        return bundle

    class Session:
        async def get(self, _model, _document_id):
            return target

    monkeypatch.setattr(review_service, "load_revision_bundle", fake_load_revision_bundle)
    with pytest.raises(HTTPException) as exc_info:
        await review_service.create_relation_proposal(
            Session(),
            revision_id="rev-v2",
            target_document_id="doc-target",
            relation_type="amends",
            actor_user_id="admin-v2",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_legal_kb_reset_node_review_endpoint_calls_review_service(client, monkeypatch):
    calls: list[dict[str, str | None]] = []

    async def fake_reset_canonical_node_review(_session, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            node_id="node-v2",
            revision_id="rev-v2",
            parent_id=None,
            node_type="table",
            label="Bang 1",
            text="Cot A | Cot B",
            order_index=8,
            review_status="needs_review",
            provenance={"source_order": 8},
            structured_content={"chunk_type": "table"},
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.reset_canonical_node_review", fake_reset_canonical_node_review)

    response = await client.post(
        "/api/v1/admin/legal-kb/nodes/node-v2/reset-review",
        json={"note": "Hoan tac de review lai theo nhom"},
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "needs_review"
    assert calls == [
        {
            "node_id": "node-v2",
            "actor_user_id": "11111111-1111-1111-1111-111111111111",
            "note": "Hoan tac de review lai theo nhom",
        }
    ]


@pytest.mark.asyncio
async def test_legal_kb_bulk_risky_review_endpoint_returns_revision_detail(client, monkeypatch):
    calls: list[dict[str, str | None]] = []

    async def fake_bulk_review_risky_nodes(_session, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            document=SimpleNamespace(
                document_id="doc-v2",
                title="Nghi dinh 67",
                document_number="67/2023/ND-CP",
                document_type="NGHI_DINH",
                issuing_authority="Chinh phu",
                issued_date=date(2023, 9, 6),
                effective_date=date(2023, 9, 6),
                expiry_date=None,
                legal_status="unknown",
            ),
            revision=SimpleNamespace(
                revision_id="rev-v2",
                document_id="doc-v2",
                revision_number=1,
                ingestion_status="parsed",
                review_status="in_review",
                publication_status="draft",
                checksum_sha256="abc",
                source_url="https://example.test/67.docx",
                source_downloaded_at=date(2026, 7, 3),
                source_note="note",
                parser_version="test",
                uploaded_at=datetime(2026, 7, 3, tzinfo=UTC),
                canonical_nodes=[],
                metadata_proposals=[],
                retrieval_units=[],
                review_events=[],
                standard_summaries=[],
            ),
            source_asset=None,
            relations=[],
            summary=None,
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.bulk_review_risky_nodes", fake_bulk_review_risky_nodes)
    monkeypatch.setattr("src.api.v1.admin_legal_kb.collect_publish_blockers", lambda _bundle: [])

    response = await client.post(
        "/api/v1/admin/legal-kb/revisions/rev-v2/risky-nodes/bulk-review",
        json={"node_type": "table", "mode": "review_only", "note": "Duyet theo nhom"},
    )

    assert response.status_code == 200
    assert response.json()["revision"]["revision_id"] == "rev-v2"
    assert calls == [
        {
            "revision_id": "rev-v2",
            "node_type": "table",
            "mode": "review_only",
            "actor_user_id": "11111111-1111-1111-1111-111111111111",
            "note": "Duyet theo nhom",
        }
    ]


@pytest.mark.asyncio
async def test_legal_kb_admin_source_download_serves_suspended_revision_source(client, tmp_path, monkeypatch):
    source_file = tmp_path / "fresh.docx"
    source_file.write_bytes(b"admin-source")
    monkeypatch.setattr("src.api.v1.admin_legal_kb.settings.KB_LOCAL_STORAGE_PATH", str(tmp_path))

    async def fake_load_revision_bundle(_session, revision_id: str):
        assert revision_id == "rev-v2"
        return SimpleNamespace(
            source_asset=SimpleNamespace(
                storage_uri=str(source_file),
                original_filename="fresh.docx",
            )
        )

    monkeypatch.setattr("src.api.v1.admin_legal_kb.load_revision_bundle", fake_load_revision_bundle)

    response = await client.get("/api/v1/admin/legal-kb/revisions/rev-v2/source")

    assert response.status_code == 200
    assert response.content == b"admin-source"
    assert response.headers["content-disposition"].startswith("attachment;")


@pytest.mark.asyncio
async def test_legal_kb_update_published_document_metadata_endpoint(client, monkeypatch):
    class _Session:
        def __init__(self):
            self.added = []
            self.committed = False

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

    session = _Session()

    async def override_session():
        yield session

    bundle = SimpleNamespace(
        document=SimpleNamespace(
            document_id="doc-v2",
            title="Van ban cu",
            document_number="12/2026/TT-BGTVT",
            document_type="THONG_TU",
            issuing_authority="Bo GTVT",
            issued_date=date(2026, 7, 1),
            effective_date=date(2026, 8, 1),
            expiry_date=None,
            legal_status="active",
            metadata_json={"document_role": "base"},
        ),
        revision=SimpleNamespace(
            revision_id="rev-v2",
            document_id="doc-v2",
            revision_number=1,
            ingestion_status="parsed",
            review_status="approved",
            publication_status="published",
            checksum_sha256="abc",
            source_url="https://example.test/old.docx",
            source_downloaded_at=date(2026, 7, 2),
            source_note="ghi chu cu",
            parser_version="test",
            uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
            canonical_nodes=[],
            metadata_proposals=[],
            retrieval_units=[],
            review_events=[],
            standard_summaries=[],
        ),
        source_asset=SimpleNamespace(
            asset_id="asset-v2",
            document_id="doc-v2",
            revision_id="rev-v2",
            asset_role="source",
            storage_uri="file:///tmp/fresh.docx",
            original_filename="fresh.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256="abc",
            file_size_bytes=10,
            source_url="https://example.test/old.docx",
            source_downloaded_at=date(2026, 7, 2),
            source_note="ghi chu cu",
        ),
        relations=[],
        summary=None,
    )

    async def fake_load_managed_document_bundle(_session, document_id: str):
        assert document_id == "doc-v2"
        return bundle

    monkeypatch.setattr("src.api.v1.admin_legal_kb._load_managed_document_bundle", fake_load_managed_document_bundle)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.patch(
            "/api/v1/admin/legal-kb/documents/doc-v2",
            json={
                "title": "Van ban moi",
                "source_url": "https://example.test/new.docx",
                "source_note": "ghi chu moi",
                "document_role": "guidance",
            },
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert bundle.document.title == "Van ban moi"
    assert bundle.document.metadata_json["document_role"] == "guidance"
    assert bundle.revision.source_url == "https://example.test/new.docx"
    assert bundle.source_asset.source_note == "ghi chu moi"
    assert session.committed is True


@pytest.mark.asyncio
async def test_legal_kb_update_published_document_status_endpoint(client, monkeypatch):
    class _Session:
        def __init__(self):
            self.added = []
            self.committed = False

        def add(self, obj):
            self.added.append(obj)

        async def commit(self):
            self.committed = True

    session = _Session()

    async def override_session():
        yield session

    retrieval_unit = SimpleNamespace(
        retrieval_unit_id="unit-v2",
        canonical_node_id="node-v2",
        document_id="doc-v2",
        revision_id="rev-v2",
        metadata_json={"answerable": True},
        effective_from=None,
        effective_to=None,
        answerable_status="active",
        citation_label="Điều 1",
        embedding_model=None,
        embedding_version=None,
        index_version="legal_kb_v1",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    bundle = SimpleNamespace(
        document=SimpleNamespace(
            document_id="doc-v2",
            title="Van ban cu",
            document_number="12/2026/TT-BGTVT",
            document_type="THONG_TU",
            issuing_authority="Bo GTVT",
            issued_date=date(2026, 7, 1),
            effective_date=date(2026, 7, 1),
            expiry_date=None,
            legal_status="active",
            metadata_json={},
        ),
        revision=SimpleNamespace(
            revision_id="rev-v2",
            document_id="doc-v2",
            revision_number=1,
            ingestion_status="parsed",
            review_status="approved",
            publication_status="published",
            checksum_sha256="abc",
            source_url="https://example.test/docx",
            source_downloaded_at=date(2026, 7, 2),
            source_note="note",
            parser_version="test",
            uploaded_at=datetime(2026, 7, 2, tzinfo=UTC),
            canonical_nodes=[],
            metadata_proposals=[],
            retrieval_units=[retrieval_unit],
            review_events=[],
            standard_summaries=[],
        ),
        source_asset=None,
        relations=[],
        summary=None,
    )

    async def fake_load_managed_document_bundle(_session, document_id: str):
        assert document_id == "doc-v2"
        return bundle

    monkeypatch.setattr("src.api.v1.admin_legal_kb._load_managed_document_bundle", fake_load_managed_document_bundle)
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.post(
            "/api/v1/admin/legal-kb/documents/doc-v2/status",
            json={"status": "replaced", "replacement_document_id": "doc-new"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert bundle.document.legal_status == "expired"
    assert bundle.document.metadata_json["lifecycle_label"] == "replaced"
    assert bundle.document.metadata_json["replacement_document_id"] == "doc-new"
    assert retrieval_unit.answerable_status == "historical"
    assert session.committed is True
