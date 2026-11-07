from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "src"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_chat_runtime_does_not_import_legacy_retrieval_module():
    nodes_source = _read("rag/agent/nodes/__init__.py")
    tools_source = _read("rag/agent/tools/__init__.py")

    assert "from src.rag.retrieval.hybrid import" not in nodes_source
    assert "from src.rag.retrieval.hybrid import" not in tools_source
    assert "hybrid_retrieve_legal" in tools_source


def test_public_documents_runtime_does_not_reference_legacy_document_models():
    documents_source = _read("api/v1/documents.py")

    assert "from src.models.legal_document import LegalDocument" not in documents_source
    assert "from src.models.document_chunk import DocumentChunk" not in documents_source
    assert "LegalKbDocument" in documents_source


def test_runtime_does_not_mount_or_import_legacy_admin_queue_route():
    main_source = _read("main.py")
    reconcile_source = _read("db/reconcile_uploaded_documents.py")

    assert "admin_legal_kb" in main_source
    assert "from src.api.v1.admin_kb import" not in main_source
    assert "include_router(admin_kb_router" not in main_source
    assert "from src.api.v1.admin_kb import" not in reconcile_source
    assert "legacy_kb_support" in reconcile_source


def test_legacy_scripts_require_explicit_opt_in_flag():
    publish_source = _read("db/publish_effective_documents.py")
    reconcile_source = _read("db/reconcile_uploaded_documents.py")

    assert "--legacy-allow" in publish_source
    assert "--legacy-allow" in reconcile_source
