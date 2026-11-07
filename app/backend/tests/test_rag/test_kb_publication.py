from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.legal_kb.publication import (
    NO_ANSWERABLE_NODE_BLOCKER,
    collect_publish_blockers,
    publish_revision,
    suspend_revision,
)
from src.legal_kb.retrieval_units import (
    GeneratedRetrievalUnits,
    build_retrieval_units,
    citation_label_for_node,
)
from src.legal_kb.review import (
    normalize_legacy_revision_review_state,
    review_metadata_proposal,
    review_summary,
)
from src.models.legal_kb import (
    LegalKbNode,
    LegalKbRevision,
    LegalKbDocument,
    LegalKbMetadataProposal,
    LegalKbRetrievalUnit,
    LegalKbSourceAsset,
    LegalKbSummary,
)


class _Session:
    def __init__(self):
        self.added: list[object] = []
        self.executed: list[object] = []
        self.committed = False
        self.rolled_back = False

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt):
        self.executed.append(stmt)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _FailingCommitSession(_Session):
    async def commit(self):
        raise RuntimeError("commit failed")


class _ReviewSummarySession(_Session):
    def __init__(self, summary):
        super().__init__()
        self.summary = summary

    async def get(self, model, entity_id):
        if model is LegalKbSummary and entity_id == self.summary.summary_id:
            return self.summary
        return None


class _ReviewMetadataSession(_Session):
    def __init__(self, proposal):
        super().__init__()
        self.proposal = proposal

    async def get(self, model, entity_id):
        if model is LegalKbMetadataProposal and entity_id == self.proposal.proposal_id:
            return self.proposal
        return None


def _proposal(*, field_name: str, proposed_value: str, review_status: str = "approved") -> LegalKbMetadataProposal:
    return LegalKbMetadataProposal(
        proposal_id=f"proposal-{field_name}-{proposed_value}",
        document_id="doc-1",
        revision_id="rev-1",
        field_name=field_name,
        proposed_value=proposed_value,
        source_type="upload",
        review_status=review_status,
    )


def _base_bundle():
    document = LegalKbDocument(
        document_id="doc-1",
        title="Thong tu thu nghiem",
        document_type="THONG_TU",
        issuing_authority="Bo GTVT",
        issued_date=date(2026, 7, 1),
        effective_date=date(2026, 8, 1),
        legal_status="unknown",
        metadata_json={"document_role": "original"},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="in_review",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    source_asset = LegalKbSourceAsset(
        asset_id="asset-1",
        document_id="doc-1",
        revision_id="rev-1",
        asset_role="source",
        storage_uri="file:///legal-kb/doc-1/rev-1/source.docx",
        original_filename="source.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="abc123",
        metadata_json={"storage_backend": "local"},
    )
    node = LegalKbNode(
        node_id="node-1",
        revision_id="rev-1",
        node_type="article",
        label="Dieu 1",
        text="Nguoi lai xe phai mang theo giay to hop le.",
        order_index=1,
        review_status="approved",
    )
    summary = LegalKbSummary(
        summary_id="summary-1",
        document_id="doc-1",
        revision_id="rev-1",
        content="Thong tu nay quy dinh nghia vu mang theo giay to.",
        review_status="approved",
    )
    revision.canonical_nodes = [node]
    revision.metadata_proposals = [
        _proposal(field_name="title", proposed_value="Thong tu thu nghiem"),
        _proposal(field_name="document_type", proposed_value="THONG_TU"),
        _proposal(field_name="issuing_authority", proposed_value="Bo GTVT"),
        _proposal(field_name="issued_date", proposed_value="2026-07-01"),
        _proposal(field_name="effective_date", proposed_value="2026-08-01"),
        _proposal(field_name="document_role", proposed_value="original"),
    ]
    revision.standard_summaries = [summary]
    revision.retrieval_units = []
    revision.review_events = []
    document.outgoing_relations = []
    document.incoming_relations = []
    return SimpleNamespace(
        document=document,
        revision=revision,
        source_asset=source_asset,
        summary=summary,
        relations=[],
    )


def test_collect_publish_blockers_flags_conflict_and_amendment_relation_gap():
    bundle = _base_bundle()
    bundle.document.metadata_json["document_role"] = "amendment"
    for proposal in bundle.revision.metadata_proposals:
        if proposal.field_name == "document_role":
            proposal.proposed_value = "amendment"
    bundle.revision.metadata_proposals.append(
        _proposal(field_name="title", proposed_value="Thong tu xung dot", review_status="needs_review")
    )
    bundle.summary.review_status = "needs_review"
    bundle.revision.canonical_nodes[0].review_status = "needs_review"

    blockers = collect_publish_blockers(bundle)

    assert "Metadata conflict is unresolved: title." in blockers
    assert "Summary proposal is not approved." in blockers
    assert "Canonical nodes still need admin review." in blockers
    assert "Amendment relation is unresolved." in blockers


def test_collect_publish_blockers_flags_orphan_clause_locator():
    bundle = _base_bundle()
    bundle.revision.canonical_nodes = [
        LegalKbNode(
            node_id="orphan-clause",
            revision_id="rev-1",
            node_type="clause",
            label="Khoan 1",
            text="Khoan khong co Dieu cha.",
            order_index=1,
            review_status="approved",
            parent_id=None,
            structured_content={"article_num": "1", "clause_num": "1"},
        )
    ]

    blockers = collect_publish_blockers(bundle)

    assert any("Kho" in blocker and "cha" in blocker for blocker in blockers)


def test_collect_publish_blockers_uses_approved_revision_role_for_replacement():
    bundle = _base_bundle()
    bundle.document.metadata_json["document_role"] = "original"
    for proposal in bundle.revision.metadata_proposals:
        if proposal.field_name == "document_role":
            proposal.proposed_value = "amendment"

    blockers = collect_publish_blockers(bundle)

    assert "Amendment relation is unresolved." in blockers


@pytest.mark.asyncio
async def test_review_metadata_for_replacement_draft_does_not_mutate_published_document(monkeypatch):
    bundle = _base_bundle()
    bundle.document.title = "Old published title"
    bundle.document.legal_status = "active"
    bundle.revision.revision_number = 2
    proposal = _proposal(
        field_name="title",
        proposed_value="New replacement title",
        review_status="needs_review",
    )
    bundle.revision.metadata_proposals = [proposal]
    session = _ReviewMetadataSession(proposal)

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == bundle.revision.revision_id
        return bundle

    monkeypatch.setattr("src.legal_kb.review.load_revision_bundle", fake_load_revision_bundle)

    reviewed = await review_metadata_proposal(
        session,
        proposal_id=proposal.proposal_id,
        decision="approved",
        actor_user_id="admin-1",
    )

    assert reviewed.review_status == "approved"
    assert bundle.document.title == "Old published title"
    assert bundle.revision.review_status == "in_review"
    assert session.committed is True


def test_collect_publish_blockers_requires_answerability_decision_for_risky_nodes():
    bundle = _base_bundle()
    table = LegalKbNode(
        node_id="node-table",
        revision_id="rev-1",
        node_type="table",
        label="Bang 1",
        text="Cot A | Cot B",
        order_index=2,
        review_status="approved",
        structured_content={},
    )
    bundle.revision.canonical_nodes.append(table)

    blockers = collect_publish_blockers(bundle)

    assert "Approved table/form/appendix/image nodes need answerable or review-only decision." in blockers


def test_normalize_legacy_revision_review_state_auto_approves_upload_metadata_and_safe_nodes():
    bundle = _base_bundle()
    bundle.revision.metadata_proposals = [
        _proposal(field_name="title", proposed_value="Thong tu thu nghiem", review_status="needs_review"),
        _proposal(field_name="document_type", proposed_value="THONG_TU", review_status="needs_review"),
        _proposal(field_name="issuing_authority", proposed_value="Bo GTVT", review_status="needs_review"),
        _proposal(field_name="issued_date", proposed_value="2026-07-01", review_status="needs_review"),
        _proposal(field_name="effective_date", proposed_value="2026-08-01", review_status="needs_review"),
        _proposal(field_name="document_role", proposed_value="original", review_status="needs_review"),
    ]
    safe_article = LegalKbNode(
        node_id="node-safe",
        revision_id="rev-1",
        node_type="article",
        label="Dieu 2",
        text="Noi dung dieu hai.",
        order_index=2,
        review_status="needs_review",
    )
    risky_table = LegalKbNode(
        node_id="node-risky",
        revision_id="rev-1",
        node_type="table",
        label="Bang 1",
        text="Cot A | Cot B",
        order_index=3,
        review_status="needs_review",
        structured_content={},
    )
    bundle.revision.canonical_nodes = [safe_article, risky_table]

    changed = normalize_legacy_revision_review_state(bundle)

    assert changed is True
    assert all(proposal.review_status == "approved" for proposal in bundle.revision.metadata_proposals)
    assert bundle.document.title == "Thong tu thu nghiem"
    assert bundle.document.document_type == "THONG_TU"
    assert safe_article.review_status == "approved"
    assert risky_table.review_status == "needs_review"


@pytest.mark.asyncio
async def test_build_retrieval_units_embeds_only_answerable_nodes(monkeypatch):
    document = LegalKbDocument(
        document_id="doc-1",
        title="Thong tu thu nghiem",
        document_type="THONG_TU",
        issuing_authority="Bo GTVT",
        effective_date=date(2026, 7, 1),
        legal_status="active",
        metadata_json={},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    article = LegalKbNode(
        node_id="node-1",
        revision_id="rev-1",
        node_type="article",
        label="Dieu 1",
        text="Noi dung dieu mot.",
        order_index=1,
        review_status="approved",
    )
    image = LegalKbNode(
        node_id="node-2",
        revision_id="rev-1",
        parent_id="node-1",
        node_type="image_caption",
        label="Hinh 1",
        text="Anh minh hoa.",
        order_index=2,
        review_status="approved",
    )
    revision.canonical_nodes = [article, image]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr("src.legal_kb.retrieval_units.embed_texts", fake_embed_texts)

    generated = await build_retrieval_units(document=document, revision=revision)

    assert generated.answerable_count == 1
    assert len(generated.units) == 2
    assert generated.units[0].answerable_status in {"active", "future", "historical"}
    assert generated.units[0].embedding_vector is not None
    assert generated.units[1].answerable_status == "not_answerable"
    assert generated.units[1].embedding_vector is None


@pytest.mark.asyncio
async def test_build_retrieval_units_embeds_reviewed_answerable_table(monkeypatch):
    document = LegalKbDocument(
        document_id="doc-1",
        title="Thong tu thu nghiem",
        document_type="THONG_TU",
        issuing_authority="Bo GTVT",
        effective_date=date(2026, 7, 1),
        legal_status="active",
        metadata_json={},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    table = LegalKbNode(
        node_id="node-table",
        revision_id="rev-1",
        node_type="table",
        label="Bang 1",
        text="Muc phat | Hanh vi",
        order_index=1,
        review_status="approved",
        structured_content={"answerable": True},
    )
    revision.canonical_nodes = [table]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr("src.legal_kb.retrieval_units.embed_texts", fake_embed_texts)

    generated = await build_retrieval_units(document=document, revision=revision)

    assert generated.answerable_count == 1
    assert generated.units[0].answerable_status in {"active", "future", "historical"}
    assert generated.units[0].embedding_vector is not None


@pytest.mark.asyncio
async def test_build_retrieval_units_uses_unique_content_hash_per_node(monkeypatch):
    document = LegalKbDocument(
        document_id="doc-1",
        title="Luat thu nghiem",
        document_type="LUAT",
        issuing_authority="Quoc hoi",
        effective_date=date(2026, 7, 1),
        legal_status="active",
        metadata_json={},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    clause_a = LegalKbNode(
        node_id="node-a",
        revision_id="rev-1",
        node_type="clause",
        label="Khoan 4",
        text="Chinh phu quy dinh chi tiet Dieu nay.",
        order_index=1,
        review_status="approved",
    )
    clause_b = LegalKbNode(
        node_id="node-b",
        revision_id="rev-1",
        node_type="clause",
        label="Khoan 4",
        text="Chinh phu quy dinh chi tiet Dieu nay.",
        order_index=2,
        review_status="approved",
    )
    revision.canonical_nodes = [clause_a, clause_b]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr("src.legal_kb.retrieval_units.embed_texts", fake_embed_texts)

    generated = await build_retrieval_units(document=document, revision=revision)

    assert len(generated.units) == 2
    assert generated.units[0].content_hash != generated.units[1].content_hash


@pytest.mark.asyncio
async def test_build_retrieval_units_uses_structured_locator_over_stale_parent(monkeypatch):
    document = LegalKbDocument(
        document_id="doc-1",
        title="Nghi dinh thu nghiem",
        document_type="NGHI_DINH",
        issuing_authority="Chinh phu",
        effective_date=date(2026, 7, 1),
        legal_status="active",
        metadata_json={},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    stale_parent = LegalKbNode(
        node_id="node-article-49",
        revision_id="rev-1",
        node_type="article",
        label="Dieu 49",
        text="Noi dung dieu 49.",
        order_index=1,
        review_status="approved",
        structured_content={"chapter_num": 3, "article_num": 49, "chunk_type": "dieu"},
    )
    clause_50 = LegalKbNode(
        node_id="node-clause-50",
        revision_id="rev-1",
        parent_id="node-article-49",
        node_type="clause",
        label="Khoan 1",
        text="Nguyen tac tru diem giay phep lai xe.",
        order_index=2,
        review_status="approved",
        structured_content={
            "chapter_num": 3,
            "article_num": 50,
            "clause_num": 1,
            "chunk_type": "khoan",
        },
    )
    point_51 = LegalKbNode(
        node_id="node-point-51",
        revision_id="rev-1",
        parent_id="node-article-49",
        node_type="point",
        label="Diem a",
        text="Du lieu diem duoc phuc hoi tu dong.",
        order_index=3,
        review_status="approved",
        structured_content={
            "chapter_num": 3,
            "article_num": 51,
            "clause_num": 3,
            "point_num": "a",
            "chunk_type": "diem",
        },
    )
    revision.canonical_nodes = [stale_parent, clause_50, point_51]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr("src.legal_kb.retrieval_units.embed_texts", fake_embed_texts)

    generated = await build_retrieval_units(document=document, revision=revision)

    labels = [unit.citation_label for unit in generated.units]
    assert labels == [
        "Chương 3 > Điều 49",
        "Chương 3 > Điều 50 > khoản 1",
        "Chương 3 > Điều 51 > khoản 3 > điểm a",
    ]
    assert "Điều 50" in generated.units[1].text
    assert "Điều 49 > khoản 1" not in generated.units[1].text


def test_citation_label_for_node_uses_structured_locator_without_parent_map():
    node = LegalKbNode(
        node_id="node-1",
        revision_id="rev-1",
        node_type="point",
        label="Diem b",
        text="Noi dung diem b.",
        order_index=1,
        review_status="approved",
        structured_content={
            "chapter_num": 2,
            "article_num": "4a",
            "clause_num": 3,
            "point_num": "b",
        },
    )

    assert citation_label_for_node(node=node) == "Chương 2 > Điều 4a > khoản 3 > điểm b"


def test_citation_label_for_node_fits_database_length_for_long_fallback_chain():
    nodes: list[LegalKbNode] = []
    parent_id = None
    for index in range(10):
        node = LegalKbNode(
            node_id=f"node-{index}",
            revision_id="rev-1",
            parent_id=parent_id,
            node_type="form",
            label="Phu luc / bieu mau doi chieu",
            text="Noi dung bieu mau.",
            order_index=index,
            review_status="approved",
            structured_content={"review_only": True, "answerable": False},
        )
        nodes.append(node)
        parent_id = node.node_id
    parent_map = {node.node_id: node for node in nodes}

    label = citation_label_for_node(node=nodes[-1], parent_map=parent_map)

    assert len(label) <= 255
    assert label == "Phu luc / bieu mau doi chieu > Node 9"


def test_rebuild_citation_audit_detects_legacy_mismatched_units():
    from scripts.rebuild_kb_citations import _audit_revision

    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="published",
        uploaded_at=datetime.now(tz=UTC),
    )
    node = LegalKbNode(
        node_id="node-50",
        revision_id="rev-1",
        node_type="clause",
        label="Khoan 1",
        text="Nguyen tac tru diem giay phep lai xe.",
        order_index=1,
        review_status="approved",
        structured_content={"chapter_num": 3, "article_num": 50, "clause_num": 1},
    )
    unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-1",
        canonical_node_id="node-50",
        document_id="doc-1",
        revision_id="rev-1",
        text="Trich dan: Chuong 3 > Dieu 49 > Khoan 1",
        answerable_status="active",
        citation_label="Chuong 3 > Dieu 49 > Khoan 1",
        content_hash="hash-1",
    )
    unit.canonical_node = node
    revision.canonical_nodes = [node]
    revision.retrieval_units = [unit]

    active_units, mismatched_units, labels_to_change, answerable_nodes = _audit_revision(revision)

    assert active_units == 1
    assert mismatched_units == 1
    assert labels_to_change == 1
    assert answerable_nodes == 1


@pytest.mark.asyncio
async def test_build_retrieval_units_keeps_review_only_nodes_out_of_answerable(monkeypatch):
    document = LegalKbDocument(
        document_id="doc-1",
        title="Luat thu nghiem",
        document_type="LUAT",
        issuing_authority="Quoc hoi",
        effective_date=date(2026, 7, 1),
        legal_status="active",
        metadata_json={},
    )
    revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="draft",
        uploaded_at=datetime.now(tz=UTC),
    )
    review_only_table = LegalKbNode(
        node_id="node-header",
        revision_id="rev-1",
        node_type="table",
        label="Quoc hieu, tieu ngu",
        text="CONG HOA XA HOI CHU NGHIA VIET NAM",
        order_index=1,
        review_status="approved",
        structured_content={"review_only": True, "review_only_role": "national_header", "answerable": False},
    )
    article = LegalKbNode(
        node_id="node-article",
        revision_id="rev-1",
        node_type="article",
        label="Dieu 1",
        text="Luat nay quy dinh ve hoat dong duong bo.",
        order_index=2,
        review_status="approved",
    )
    revision.canonical_nodes = [review_only_table, article]

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr("src.legal_kb.retrieval_units.embed_texts", fake_embed_texts)

    generated = await build_retrieval_units(document=document, revision=revision)

    assert generated.answerable_count == 1
    assert len(generated.units) == 2
    assert generated.units[0].answerable_status == "not_answerable"
    assert generated.units[0].embedding_vector is None
    assert generated.units[1].embedding_vector is not None


def test_collect_publish_blockers_skips_answerability_for_review_only_tables():
    bundle = _base_bundle()
    header_table = LegalKbNode(
        node_id="node-header",
        revision_id="rev-1",
        node_type="table",
        label="Quoc hieu, tieu ngu",
        text="CONG HOA XA HOI CHU NGHIA VIET NAM",
        order_index=2,
        review_status="approved",
        structured_content={"review_only": True, "review_only_role": "national_header", "answerable": False},
    )
    bundle.revision.canonical_nodes.append(header_table)

    blockers = collect_publish_blockers(bundle)

    assert "Approved table/form/appendix/image nodes need answerable or review-only decision." not in blockers


def test_collect_publish_blockers_requires_at_least_one_answerable_node():
    bundle = _base_bundle()
    bundle.revision.canonical_nodes = [
        LegalKbNode(
            node_id="node-review-only-table",
            revision_id="rev-1",
            node_type="table",
            label="Bang doi chieu",
            text="Bang muc phat can doi chieu lai.",
            order_index=1,
            review_status="approved",
            structured_content={"review_only": True, "answerable": False},
        )
    ]

    blockers = collect_publish_blockers(bundle)

    assert NO_ANSWERABLE_NODE_BLOCKER in blockers


@pytest.mark.asyncio
async def test_publish_revision_blocks_before_embedding_when_no_answerable_nodes(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.canonical_nodes = [
        LegalKbNode(
            node_id="node-review-only-table",
            revision_id="rev-1",
            node_type="table",
            label="Bang doi chieu",
            text="Bang muc phat can doi chieu lai.",
            order_index=1,
            review_status="approved",
            structured_content={"review_only": True, "answerable": False},
        )
    ]
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        assert _kwargs == {"for_update": True}
        return bundle

    async def fail_build_retrieval_units(*, document, revision):
        raise AssertionError("publish should stop at publish blockers before building retrieval units")

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fail_build_retrieval_units)

    with pytest.raises(HTTPException) as exc_info:
        await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert exc_info.value.status_code == 409
    assert NO_ANSWERABLE_NODE_BLOCKER in exc_info.value.detail["blockers"]


@pytest.mark.asyncio
async def test_publish_revision_marks_revision_and_persists_retrieval_units(monkeypatch):
    bundle = _base_bundle()
    session = _Session()
    unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-1",
        canonical_node_id="node-1",
        document_id="doc-1",
        revision_id="rev-1",
        text="retrieval text",
        answerable_status="active",
        citation_label="Dieu 1",
        content_hash="hash-1",
        embedding_model="text-embedding-3-small",
        embedding_version="legal_kb_v1",
        index_version="legal_kb_v1",
    )

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    async def fake_build_retrieval_units(*, document, revision):
        assert document.document_id == "doc-1"
        assert revision.revision_id == "rev-1"
        return GeneratedRetrievalUnits(units=[unit], answerable_count=1)

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fake_build_retrieval_units)

    revision, blockers = await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert blockers == []
    assert revision.publication_status == "published"
    assert revision.review_status == "approved"


@pytest.mark.asyncio
async def test_publish_revision_rolls_back_when_database_commit_fails(monkeypatch):
    bundle = _base_bundle()
    session = _FailingCommitSession()
    unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-1",
        canonical_node_id="node-1",
        document_id="doc-1",
        revision_id="rev-1",
        text="retrieval text",
        answerable_status="active",
        citation_label="Dieu 1",
        content_hash="hash-1",
    )

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    async def fake_build_retrieval_units(*, document, revision):
        return GeneratedRetrievalUnits(units=[unit], answerable_count=1)

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fake_build_retrieval_units)

    with pytest.raises(RuntimeError, match="commit failed"):
        await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_publish_revision_is_idempotent_when_revision_is_already_published(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.publication_status = "published"
    bundle.revision.review_status = "approved"
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    async def fail_build_retrieval_units(*, document, revision):
        raise AssertionError("an idempotent publish must not rebuild retrieval units")

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fail_build_retrieval_units)

    revision, blockers = await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert revision is bundle.revision
    assert blockers == []
    assert session.committed is False
    assert session.added == []


@pytest.mark.asyncio
async def test_publish_revision_blocks_published_revision_with_orphan_locator(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.publication_status = "published"
    bundle.revision.review_status = "approved"
    bundle.revision.canonical_nodes = [
        LegalKbNode(
            node_id="orphan-clause",
            revision_id="rev-1",
            node_type="clause",
            label="1",
            text="Khoan khong co dieu cha.",
            order_index=1,
            review_status="approved",
            parent_id=None,
        )
    ]
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    async def fail_build_retrieval_units(*, document, revision):
        raise AssertionError("published revision with orphan locator must stop before rebuild")

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fail_build_retrieval_units)

    with pytest.raises(HTTPException) as exc_info:
        await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert exc_info.value.status_code == 409
    assert any("Kho" in blocker and "cha" in blocker for blocker in exc_info.value.detail["blockers"])
    assert session.committed is False


@pytest.mark.asyncio
async def test_publish_revision_normalizes_published_revision_review_status(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.publication_status = "published"
    bundle.revision.review_status = "in_review"
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    async def fail_build_retrieval_units(*, document, revision):
        raise AssertionError("normalizing an already-published revision must not rebuild retrieval units")

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fail_build_retrieval_units)

    revision, blockers = await publish_revision(session, revision_id="rev-1", actor_user_id="admin-1")

    assert revision.review_status == "approved"
    assert blockers == []
    assert session.committed is True
    assert len(session.added) == 1
    assert session.added[0].decision == "updated"


@pytest.mark.asyncio
async def test_publish_replacement_revision_archives_previous_revision(monkeypatch):
    bundle = _base_bundle()
    bundle.document.title = "Old published title"
    bundle.revision.revision_id = "rev-2"
    bundle.revision.revision_number = 2
    for proposal in bundle.revision.metadata_proposals:
        if proposal.field_name == "title":
            proposal.proposed_value = "New replacement title"
    old_unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-old",
        canonical_node_id="node-old",
        document_id="doc-1",
        revision_id="rev-1",
        text="old retrieval text",
        answerable_status="active",
        citation_label="Dieu 1",
        content_hash="hash-old",
    )
    old_revision = LegalKbRevision(
        revision_id="rev-1",
        document_id="doc-1",
        revision_number=1,
        ingestion_status="parsed",
        review_status="approved",
        publication_status="published",
        uploaded_at=datetime.now(tz=UTC),
    )
    old_revision.retrieval_units = [old_unit]
    bundle.document.revisions = [old_revision, bundle.revision]
    session = _Session()
    new_unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-new",
        canonical_node_id="node-1",
        document_id="doc-1",
        revision_id="rev-2",
        text="new retrieval text",
        answerable_status="active",
        citation_label="Dieu 1",
        content_hash="hash-new",
    )

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-2"
        return bundle

    async def fake_build_retrieval_units(*, document, revision):
        assert document.document_id == "doc-1"
        assert document.title == "New replacement title"
        assert revision.revision_id == "rev-2"
        return GeneratedRetrievalUnits(units=[new_unit], answerable_count=1)

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fake_build_retrieval_units)

    revision, blockers = await publish_revision(session, revision_id="rev-2", actor_user_id="admin-1")

    assert blockers == []
    assert revision.publication_status == "published"
    assert bundle.document.title == "New replacement title"
    assert old_revision.publication_status == "archived"
    assert old_unit.answerable_status == "historical"


@pytest.mark.asyncio
async def test_publish_replacement_revision_does_not_apply_metadata_when_generation_blocks(monkeypatch):
    bundle = _base_bundle()
    bundle.document.title = "Old published title"
    bundle.revision.revision_id = "rev-2"
    bundle.revision.revision_number = 2
    for proposal in bundle.revision.metadata_proposals:
        if proposal.field_name == "title":
            proposal.proposed_value = "New replacement title"
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-2"
        return bundle

    async def fake_build_retrieval_units(*, document, revision):
        assert document.title == "New replacement title"
        return GeneratedRetrievalUnits(units=[], answerable_count=0)

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)
    monkeypatch.setattr("src.legal_kb.publication.build_retrieval_units", fake_build_retrieval_units)

    with pytest.raises(HTTPException) as exc_info:
        await publish_revision(session, revision_id="rev-2", actor_user_id="admin-1")

    assert exc_info.value.status_code == 409
    assert bundle.document.title == "Old published title"
    assert session.committed is False


@pytest.mark.asyncio
async def test_review_summary_keeps_published_revision_approved(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.publication_status = "published"
    bundle.revision.review_status = "in_review"
    session = _ReviewSummarySession(bundle.summary)

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    monkeypatch.setattr("src.legal_kb.review.load_revision_bundle", fake_load_revision_bundle)

    summary = await review_summary(
        session,
        summary_id="summary-1",
        decision="approved",
        actor_user_id="admin-1",
        content="Tom tat da sua.",
    )

    assert summary.content == "Tom tat da sua."
    assert summary.review_status == "approved"
    assert bundle.revision.review_status == "approved"
    assert session.committed is True


@pytest.mark.asyncio
async def test_review_summary_keeps_draft_revision_in_review(monkeypatch):
    bundle = _base_bundle()
    bundle.revision.publication_status = "draft"
    bundle.revision.review_status = "approved"
    session = _ReviewSummarySession(bundle.summary)

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    monkeypatch.setattr("src.legal_kb.review.load_revision_bundle", fake_load_revision_bundle)

    await review_summary(
        session,
        summary_id="summary-1",
        decision="approved",
        actor_user_id="admin-1",
        content=None,
    )

    assert bundle.revision.review_status == "in_review"
    assert session.committed is True


@pytest.mark.asyncio
async def test_suspend_revision_marks_units_suspended(monkeypatch):
    bundle = _base_bundle()
    unit = LegalKbRetrievalUnit(
        retrieval_unit_id="unit-1",
        canonical_node_id="node-1",
        document_id="doc-1",
        revision_id="rev-1",
        text="retrieval text",
        answerable_status="active",
        citation_label="Dieu 1",
        content_hash="hash-1",
    )
    bundle.revision.retrieval_units = [unit]
    session = _Session()

    async def fake_load_revision_bundle(_session, revision_id: str, **_kwargs):
        assert revision_id == "rev-1"
        return bundle

    monkeypatch.setattr("src.legal_kb.publication.load_revision_bundle", fake_load_revision_bundle)

    revision = await suspend_revision(
        session,
        revision_id="rev-1",
        actor_user_id="admin-1",
        reason="Sai metadata nghiem trong",
    )

    assert revision.publication_status == "suspended"
    assert bundle.document.legal_status == "suspended"
    assert unit.answerable_status == "suspended"
    assert session.committed is True
