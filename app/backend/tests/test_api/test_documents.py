from datetime import date
from types import SimpleNamespace

import pytest

from src.db.session import get_session
from src.main import app


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def one_or_none(self):
        return self.value


class _SourceSession:
    def __init__(self, row):
        self.row = row

    async def execute(self, _statement):
        return _ScalarResult(self.row)


class _ListResult:
    def __init__(self, *, scalar_value=None, rows=None):
        self.scalar_value = scalar_value
        self.rows = rows or []

    def scalar(self):
        return self.scalar_value

    def all(self):
        return self.rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def one_or_none(self):
        return self.rows[0] if self.rows else None


class _ListDocumentsSession:
    def __init__(self):
        self.calls = 0
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        self.calls += 1
        if self.calls == 1:
            return _ListResult(scalar_value=1)
        if self.calls == 3:
            return _ListResult(rows=[])
        document = SimpleNamespace(
            document_id='10010010-0100-1001-0010-010010010019',
            title='Luật Trật tự, an toàn giao thông đường bộ 2024',
            document_type='LUAT',
            legal_status='active',
            effective_date=date(2025, 1, 1),
            expiry_date=None,
            issuing_authority='Quốc hội',
        )
        revision = SimpleNamespace(
            revision_id='rev-001',
            source_url='https://example.test/source',
        )
        source_asset = SimpleNamespace(
            original_filename='luat-giao-thong.pdf',
            source_url='https://example.test/source',
        )
        return _ListResult(rows=[(document, revision, source_asset)])


class _SequenceSession:
    def __init__(self, *results):
        self.results = list(results)

    async def execute(self, _statement):
        if not self.results:
            raise AssertionError('Unexpected execute call')
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_list_documents_exposes_public_source_download_url(client, monkeypatch):
    session = _ListDocumentsSession()

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['source_file_name'] == 'luat-giao-thong.pdf'
    assert item['source_download_url'] == '/api/v1/documents/10010010-0100-1001-0010-010010010019/source'
    assert item['relations'] == []
    compiled = str(session.statements[1])
    assert 'legal_kb_legal_documents.legal_status = :legal_status_1' in compiled


@pytest.mark.asyncio
async def test_list_documents_switches_to_legal_kb_when_public_flag_enabled(client, monkeypatch):
    session = _SequenceSession(
        _ListResult(scalar_value=1),
        _ListResult(
            rows=[
                (
                    SimpleNamespace(
                        document_id='doc-v2',
                        title='Văn bản KB mới',
                        document_type='THONG_TU',
                        legal_status='active',
                        effective_date=date(2026, 8, 1),
                        expiry_date=None,
                        issuing_authority='Bộ GTVT',
                    ),
                    SimpleNamespace(
                        revision_id='rev-v2',
                        source_url='https://example.test/docx',
                    ),
                    SimpleNamespace(
                        original_filename='fresh.docx',
                        source_url='https://example.test/docx',
                    ),
                )
            ]
        ),
        _ListResult(rows=[]),
    )

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    item = response.json()['items'][0]
    assert item['doc_id'] == 'doc-v2'
    assert item['current_revision_id'] == 'rev-v2'
    assert item['viewer_warning'] is not None
    assert item['standard_summary_url'] == '/api/v1/documents/doc-v2/summary'
    assert item['source_download_url'] == '/api/v1/documents/doc-v2/source'
    assert item['relations'] == []


@pytest.mark.asyncio
async def test_list_documents_includes_public_relations(client):
    source_document = SimpleNamespace(
        document_id='doc-source',
        title='Văn bản nguồn',
        document_number='118/2025/QH15',
        document_type='LUAT',
        legal_status='active',
        effective_date=date(2026, 7, 1),
        expiry_date=None,
        issuing_authority='Quốc hội',
    )
    target_document = SimpleNamespace(
        document_id='doc-target',
        title='Văn bản liên quan',
        document_number='35/2024/QH15',
        legal_status='active',
    )
    relation = SimpleNamespace(
        relation_id='rel-1',
        source_document_id='doc-source',
        target_document_id='doc-target',
        relation_type='amends',
        source_locator='Điều 1',
        target_locator='Điều 2',
        metadata_json={'review_status': 'approved'},
        source_document=source_document,
        target_document=target_document,
    )
    session = _SequenceSession(
        _ListResult(scalar_value=1),
        _ListResult(
            rows=[
                (
                    source_document,
                    SimpleNamespace(revision_id='rev-source', source_url='https://example.test/source'),
                    SimpleNamespace(original_filename='source.docx', source_url='https://example.test/source'),
                )
            ]
        ),
        _ListResult(rows=[relation]),
    )

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    relation_payload = response.json()['items'][0]['relations'][0]
    assert relation_payload['relation_type'] == 'amends'
    assert relation_payload['direction'] == 'outgoing'
    assert relation_payload['counterpart_document_number'] == '35/2024/QH15'


@pytest.mark.asyncio
async def test_source_endpoint_serves_approved_pdf_inline(client, tmp_path, monkeypatch):
    source_file = tmp_path / 'luat-giao-thong.pdf'
    source_file.write_bytes(b'%PDF-1.4 source')
    session = _SourceSession(
        (
            SimpleNamespace(document_id='10010010-0100-1001-0010-010010010019'),
            SimpleNamespace(revision_id='rev-001'),
            SimpleNamespace(storage_uri=str(source_file), original_filename='luat-giao-thong.pdf'),
        )
    )

    async def override_session():
        yield session

    monkeypatch.setattr('src.api.v1.documents.settings.KB_LOCAL_STORAGE_PATH', str(tmp_path))
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents/10010010-0100-1001-0010-010010010019/source')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200
    assert response.content == b'%PDF-1.4 source'
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['content-disposition'].startswith('inline;')


@pytest.mark.asyncio
async def test_source_endpoint_rejects_path_outside_legal_kb_storage(client, tmp_path, monkeypatch):
    storage_dir = tmp_path / 'storage'
    storage_dir.mkdir()
    outside_file = tmp_path / 'outside.pdf'
    outside_file.write_bytes(b'not public')
    session = _SourceSession(
        (
            SimpleNamespace(document_id='10010010-0100-1001-0010-010010010019'),
            SimpleNamespace(revision_id='rev-001'),
            SimpleNamespace(storage_uri=str(outside_file), original_filename='outside.pdf'),
        )
    )

    async def override_session():
        yield session

    monkeypatch.setattr('src.api.v1.documents.settings.KB_LOCAL_STORAGE_PATH', str(storage_dir))
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents/10010010-0100-1001-0010-010010010019/source')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_source_endpoint_redirects_object_storage_source(client, monkeypatch):
    session = _SourceSession(
        (
            SimpleNamespace(document_id='10010010-0100-1001-0010-010010010019'),
            SimpleNamespace(revision_id='rev-001'),
            SimpleNamespace(storage_uri='s3://legalai/uploads/source.pdf', original_filename='source.pdf'),
        )
    )

    async def override_session():
        yield session

    class _Storage:
        def public_or_presigned_url(self, uri, *, content_disposition=None):
            assert uri == 's3://legalai/uploads/source.pdf'
            assert content_disposition == 'inline; filename="source.pdf"'
            return 'https://storage.example/source.pdf?signature=test'

    monkeypatch.setattr('src.api.v1.documents.get_object_storage', lambda: _Storage())
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get(
            '/api/v1/documents/10010010-0100-1001-0010-010010010019/source',
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 307
    assert response.headers['location'] == 'https://storage.example/source.pdf?signature=test'


@pytest.mark.asyncio
async def test_source_endpoint_requires_published_document_before_serving_source(client, tmp_path, monkeypatch):
    source_file = tmp_path / 'luat-giao-thong.pdf'
    source_file.write_bytes(b'%PDF-1.4 source')
    session = _SourceSession(None)

    async def override_session():
        yield session

    monkeypatch.setattr('src.api.v1.documents.settings.KB_LOCAL_STORAGE_PATH', str(tmp_path))
    app.dependency_overrides[get_session] = override_session
    try:
        response = await client.get('/api/v1/documents/10010010-0100-1001-0010-010010010019/source')
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_legal_kb_public_detail_returns_warning_and_summary_link(client, monkeypatch):
    async def fake_get_public_document(_session, document_id: str):
        assert document_id == 'doc-v2'
        return (
            SimpleNamespace(
                document_id='doc-v2',
                title='Van ban kho văn bản',
                document_number='12/2026/TT-BGTVT',
                document_type='THONG_TU',
                issuing_authority='Bo GTVT',
                effective_date=date(2026, 8, 1),
                expiry_date=None,
                legal_status='active',
            ),
            SimpleNamespace(revision_id='rev-v2', publication_status='published'),
            SimpleNamespace(original_filename='fresh.docx'),
        )

    monkeypatch.setattr('src.api.v1.documents._get_legal_kb_public_document', fake_get_public_document)

    response = await client.get('/api/v1/documents/doc-v2')

    assert response.status_code == 200
    payload = response.json()
    assert payload['revision_id'] == 'rev-v2'
    assert payload['source_download_url'] == '/api/v1/documents/doc-v2/source'
    assert payload['standard_summary_url'] == '/api/v1/documents/doc-v2/summary'
    assert payload['viewer_warning'] is not None


@pytest.mark.asyncio
async def test_legal_kb_source_endpoint_serves_local_source_with_warning(client, tmp_path, monkeypatch):
    source_file = tmp_path / 'fresh.docx'
    source_file.write_bytes(b'docx')
    monkeypatch.setattr('src.api.v1.documents.settings.KB_LOCAL_STORAGE_PATH', str(tmp_path))

    async def fake_get_public_document(_session, document_id: str):
        assert document_id == 'doc-v2'
        return (
            SimpleNamespace(document_id='doc-v2'),
            SimpleNamespace(revision_id='rev-v2'),
            SimpleNamespace(
                storage_uri=str(source_file),
                original_filename='fresh.docx',
            ),
        )

    monkeypatch.setattr('src.api.v1.documents._get_legal_kb_public_document', fake_get_public_document)

    response = await client.get('/api/v1/documents/doc-v2/source')

    assert response.status_code == 200
    assert response.content == b'docx'
    assert response.headers['x-legalai-viewer-warning']
    assert response.headers['content-disposition'].startswith('attachment;')
