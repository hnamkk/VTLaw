from src.core.config import Settings, settings
from src.models import KbV2DocumentRevision, KbV2LegalDocument, KbV2RetrievalUnit
from src.storage.object_storage import (
    ObjectMetadata,
    ObjectStorageError,
    S3ObjectStorage,
    build_kb_v2_object_key,
)


def test_kb_storage_settings_default_to_local_fallback():
    fresh = Settings()

    assert fresh.KB_REQUIRE_OBJECT_STORAGE is False
    assert fresh.KB_LOCAL_STORAGE_PATH == "app/backend/storage/kb_v2"


def test_kb_v2_requires_object_storage_when_flag_enabled():
    try:
        Settings(KB_REQUIRE_OBJECT_STORAGE=True, OBJECT_STORAGE_ENABLED=False)
    except ValueError as exc:
        assert "KB_REQUIRE_OBJECT_STORAGE" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected KB v2 object storage validation to fail.")


def test_kb_v2_source_key_builder_uses_immutable_layout():
    key = build_kb_v2_object_key(
        kind="source",
        document_id="doc-1",
        revision_id="rev-1",
        sha256="abc123",
        extension="docx",
    )

    assert key == "kb-v2/sources/doc-1/rev-1/abc123/source.docx"


def test_kb_v2_asset_key_builder_rejects_missing_asset_id():
    try:
        build_kb_v2_object_key(
            kind="asset",
            document_id="doc-1",
            revision_id="rev-1",
            extension="png",
        )
    except ObjectStorageError as exc:
        assert "asset_id" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected asset key builder to reject missing asset_id.")


def test_object_storage_head_object_maps_metadata():
    class _Client:
        def head_object(self, **kwargs):
            assert kwargs["Bucket"] == "legalai"
            assert kwargs["Key"] == "kb-v2/sources/doc/rev/file.docx"
            return {
                "ContentLength": 42,
                "ContentType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "ETag": '"etag"',
                "LastModified": "2026-07-02T00:00:00Z",
                "Metadata": {"sha256": "abc"},
            }

    storage = object.__new__(S3ObjectStorage)
    storage._bucket = "legalai"
    storage._client = _Client()

    result = storage.head_object("s3://legalai/kb-v2/sources/doc/rev/file.docx")

    assert result == ObjectMetadata(
        uri="s3://legalai/kb-v2/sources/doc/rev/file.docx",
        content_length=42,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        e_tag='"etag"',
        last_modified="2026-07-02T00:00:00Z",
        metadata={"sha256": "abc"},
    )


def test_object_storage_list_prefix_returns_uris():
    class _Client:
        def __init__(self):
            self.calls = 0

        def list_objects_v2(self, **kwargs):
            self.calls += 1
            assert kwargs["Bucket"] == "legalai"
            assert kwargs["Prefix"] == "kb-v2/sources/"
            if self.calls == 1:
                return {
                    "Contents": [{"Key": "kb-v2/sources/a.docx"}],
                    "IsTruncated": True,
                    "NextContinuationToken": "page-2",
                }
            assert kwargs["ContinuationToken"] == "page-2"
            return {
                "Contents": [{"Key": "kb-v2/sources/b.docx"}],
                "IsTruncated": False,
            }

    storage = object.__new__(S3ObjectStorage)
    storage._bucket = "legalai"
    storage._client = _Client()

    result = storage.list_prefix("kb-v2/sources/")

    assert result == [
        "s3://legalai/kb-v2/sources/a.docx",
        "s3://legalai/kb-v2/sources/b.docx",
    ]


def test_kb_v2_model_tables_are_registered():
    assert KbV2LegalDocument.__tablename__ == "kb_v2_legal_documents"
    assert KbV2DocumentRevision.__tablename__ == "kb_v2_document_revisions"
    assert KbV2RetrievalUnit.__tablename__ == "kb_v2_retrieval_units"


def test_kb_v2_retrieval_unit_embedding_matches_global_dimension():
    col = KbV2RetrievalUnit.__table__.c.embedding_vector
    assert col.type.dim == settings.EMBEDDING_DIM == 1536


def test_kb_v2_revision_unique_revision_number_constraint_exists():
    constraint_names = {
        constraint.name for constraint in KbV2DocumentRevision.__table__.constraints
    }
    assert "uq_kb_v2_revision_document_revision_number" in constraint_names


def test_kb_v2_document_has_legal_status_index():
    indexes = {idx.name for idx in KbV2LegalDocument.__table__.indexes}
    assert "idx_kb_v2_documents_legal_status" in indexes
