"""Unit tests for retrieval pipeline (Phase 3): scope, hybrid merge, context packer.

No database required — tests use mocked embeddings and in-memory data.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects.postgresql import ARRAY

from src.schemas.rag import RetrievedChunk, ScopeLabel


# --------------------------------------------------------------------------- #
# Scope classifier
# --------------------------------------------------------------------------- #
class TestScopeClassifier:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Hồ sơ cấp lại đăng ký xe bị mất gồm những gì?",
            "Chu kỳ kiểm định xe cơ giới được xác định thế nào?",
            "Quy định sát hạch lái xe và sức khỏe người lái xe",
            "Cách nhận biết khu đông dân cư khi đang chạy xe?",
            "Căn cứ nào quy định bốn bài sát hạch mô tô hạng A1?",
            "Biển cấm dừng có đặc điểm nhận biết nào?",
            "Đổi giấy phép A1 sang hạng A cần khám sức khỏe ra sao?",
        ],
    )
    async def test_road_domain_taxonomy_skips_embedding(self, query):
        with patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq:
            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope(query)

        assert result.label == ScopeLabel.in_scope
        assert result.score == pytest.approx(1.0)
        mock_eq.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Khung hình phạt tù cho tội phạm ma túy là bao nhiêu?",
            "Thủ tục xin hộ chiếu và thị thực gồm những gì?",
            "Cách kê khai thuế cho hóa đơn quảng cáo?",
        ],
    )
    async def test_non_road_domain_taxonomy_skips_embedding(self, query):
        with patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq:
            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope(query)

        assert result.label == ScopeLabel.out_of_scope
        assert result.score == pytest.approx(0.0)
        mock_eq.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Khung hinh phat cho toi mua ban ma tuy la bao nhieu nam tu?",
            "Gia ve may bay Ha Noi di Da Nang ngay mai bao nhieu?",
            "Toi muon hoi luat giao thong cua Singapore ve nong do con cho tai xe.",
        ],
    )
    async def test_non_road_domain_unaccented_fail_cases_skip_embedding(self, query):
        with patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq:
            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope(query)

        assert result.label == ScopeLabel.out_of_scope
        assert result.score == pytest.approx(0.0)
        mock_eq.assert_not_awaited()

    def test_cross_domain_query_is_not_forced_to_either_side(self):
        from src.rag.retrieval.scope import _domain_signals

        assert _domain_signals("Thời giờ làm việc của người lái xe vận tải đường bộ") == (
            True,
            True,
        )

    def test_explicit_legal_document_query_is_detected(self):
        from src.rag.retrieval.scope import is_explicit_legal_document_query

        assert is_explicit_legal_document_query("Cho toi thong tin ve thong tu 54/2019/TT-BGTVT")
        assert is_explicit_legal_document_query("Nghi dinh 100/2019/ND-CP quy dinh gi?")
        assert not is_explicit_legal_document_query("Cho toi thong tin ve hop dong 54/2019")

    @pytest.mark.parametrize(
        "query",
        [
            "Cho toi thong tin ve thong tu 54/2019/TT-BGTVT",
            "Cho t\u00f4i th\u00f4ng tin v\u1ec1 th\u00f4ng t\u01b0 54/2019/TT-BGTVT",
            "Thong tu 54/2019 noi ve gi?",
            "Th\u00f4ng t\u01b0 54/2019 n\u00f3i v\u1ec1 g\u00ec?",
            "TT 54/2019 con hieu luc khong?",
            "Nghi dinh 100/2019/ND-CP quy dinh gi?",
            "Ngh\u1ecb \u0111\u1ecbnh 100/2019/N\u0110-CP quy \u0111\u1ecbnh g\u00ec?",
            "Quyet dinh 23/2021/QD-BGTVT",
            "Luat 36/2024/QH15 co diem moi nao?",
            "QCVN 41:2019/BGTVT quy dinh bien bao nao?",
            "Quy chuan 41:2019/BGTVT ve bao hieu duong bo",
            "Van ban hop nhat 49/VBHN-VPQH quy dinh gi?",
            "Quy chu\u1ea9n 41:2019/BGTVT v\u1ec1 b\u00e1o hi\u1ec7u \u0111\u01b0\u1eddng b\u1ed9",
        ],
    )
    def test_explicit_legal_document_query_variants_are_detected(self, query):
        from src.rag.retrieval.scope import is_explicit_legal_document_query

        assert is_explicit_legal_document_query(query)

    @pytest.mark.parametrize(
        "query",
        [
            "Cho toi thong tin ve hop dong 54/2019",
            "Don hang 54/2019 dang o dau?",
            "Hoa don 54/2019 co can ke khai thue khong?",
            "Thoi tiet ngay 54/2019 nhu the nao?",
        ],
    )
    def test_non_legal_document_numbers_are_not_detected(self, query):
        from src.rag.retrieval.scope import is_explicit_legal_document_query

        assert not is_explicit_legal_document_query(query)

    def test_small_talk_query_is_not_out_of_scope_legal_deflection(self):
        from src.rag.retrieval.scope import is_small_talk_query

        assert is_small_talk_query("xin chào")
        assert is_small_talk_query("Hello bạn")
        assert is_small_talk_query("cảm ơn")
        assert not is_small_talk_query("xin chào, mức phạt vượt đèn đỏ là bao nhiêu?")

    @pytest.mark.asyncio
    async def test_in_scope_query(self):
        """A clear traffic law query should be classified in_scope."""
        import numpy as np

        mock_query_vec = np.random.randn(1536).astype(np.float32)
        mock_query_vec = mock_query_vec / np.linalg.norm(mock_query_vec)

        mock_ref_vecs = np.tile(mock_query_vec, (10, 1))

        with (
            patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq,
            patch("src.rag.retrieval.scope._get_ref_vectors", new_callable=AsyncMock) as mock_rv,
        ):
            mock_eq.return_value = mock_query_vec.tolist()
            mock_rv.return_value = mock_ref_vecs

            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope("mức phạt vượt đèn đỏ")

        assert result.label == ScopeLabel.in_scope
        assert result.score >= 0.72

    @pytest.mark.asyncio
    async def test_out_of_scope_query(self):
        """An unrelated query should be classified out_of_scope."""
        import numpy as np

        mock_query_vec = np.random.randn(1536).astype(np.float32)
        mock_query_vec = mock_query_vec / np.linalg.norm(mock_query_vec)

        mock_ref_vecs = np.random.randn(10, 1536).astype(np.float32)
        norms = np.linalg.norm(mock_ref_vecs, axis=1, keepdims=True)
        mock_ref_vecs = mock_ref_vecs / norms

        with (
            patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq,
            patch("src.rag.retrieval.scope._get_ref_vectors", new_callable=AsyncMock) as mock_rv,
        ):
            mock_eq.return_value = mock_query_vec.tolist()
            mock_rv.return_value = mock_ref_vecs

            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope("thời tiết hôm nay thế nào")

        assert result.score < 0.72

    @pytest.mark.asyncio
    async def test_explicit_legal_document_reference_is_forced_in_scope(self):
        import numpy as np

        mock_query_vec = np.random.randn(1536).astype(np.float32)
        mock_query_vec = mock_query_vec / np.linalg.norm(mock_query_vec)

        mock_ref_vecs = np.random.randn(10, 1536).astype(np.float32)
        norms = np.linalg.norm(mock_ref_vecs, axis=1, keepdims=True)
        mock_ref_vecs = mock_ref_vecs / norms

        with (
            patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq,
            patch("src.rag.retrieval.scope._get_ref_vectors", new_callable=AsyncMock) as mock_rv,
        ):
            mock_eq.return_value = mock_query_vec.tolist()
            mock_rv.return_value = mock_ref_vecs

            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope("Cho toi thong tin ve thong tu 54/2019/TT-BGTVT")

        assert result.label == ScopeLabel.in_scope
        assert result.score == pytest.approx(1.0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "Thong tu 54/2019 noi ve gi?",
            "Th\u00f4ng t\u01b0 54/2019 n\u00f3i v\u1ec1 g\u00ec?",
            "Luat 36/2024/QH15 co diem moi nao?",
            "QCVN 41:2019/BGTVT quy dinh bien bao nao?",
        ],
    )
    async def test_explicit_legal_document_queries_skip_embedding_scope(self, query):
        with patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq:
            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope(query)

        assert result.label == ScopeLabel.in_scope
        assert result.score == pytest.approx(1.0)
        mock_eq.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "query",
        [
            "\u0110\u01b0\u1eddng cao t\u1ed1c l\u00e0 g\u00ec?",
            "\u0110\u1ed9i m\u0169 b\u1ea3o hi\u1ec3m c\u00f3 b\u1eaft bu\u1ed9c kh\u00f4ng?",
        ],
    )
    async def test_core_road_safety_terms_skip_embedding_scope(self, query):
        with patch("src.rag.retrieval.scope.embed_query", new_callable=AsyncMock) as mock_eq:
            from src.rag.retrieval.scope import classify_scope

            result = await classify_scope(query)

        assert result.label == ScopeLabel.in_scope
        assert result.score == pytest.approx(1.0)
        mock_eq.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Hybrid merge + scoring
# --------------------------------------------------------------------------- #
class TestHybridMerge:
    @pytest.mark.asyncio
    async def test_vector_search_applies_eligibility_before_ranking(self):
        from sqlalchemy.dialects import postgresql

        from src.rag.retrieval.hybrid_legal import _vector_search

        session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
        result = await _vector_search(
            session,
            query_embedding=[0.0],
            query_date=date(2026, 1, 1),
            top_k=5,
            document_ids=None,
        )

        statement = session.execute.await_args.args[0]
        compiled = statement.compile(dialect=postgresql.dialect())
        sql = str(compiled).lower()
        assert result == []
        assert "publication_status =" in sql
        assert "legal_status =" in sql
        assert "answerable_status =" in sql
        assert "published" in compiled.params.values()
        assert list(compiled.params.values()).count("active") >= 2
        assert sql.index("where") < sql.index("order by")

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (
                "Thông tư này quy định những vấn đề chính nào?",
                "phạm vi điều chỉnh",
            ),
            (
                "Kết cấu hạ tầng đường bộ gồm những thành phần nào?",
                "giải thích từ ngữ",
            ),
        ],
    )
    def test_structural_query_expansion_is_intent_based(self, query, expected):
        from src.rag.retrieval.hybrid import expand_query_for_retrieval

        assert expected in expand_query_for_retrieval(query)

    def test_explicit_document_filter_prevents_semantic_drift(self):
        from src.rag.retrieval.hybrid import _filter_explicit_document_candidates

        candidates = [
            {"document_number": "118/2025/QH15", "chunk_id": "target"},
            {"document_number": "18/VBHN-VPQH", "chunk_id": "similar"},
        ]

        assert _filter_explicit_document_candidates(
            "Luat 118/2025/QH15 co ap dung chua?", candidates
        ) == [candidates[0]]

    def test_explicit_consolidated_document_filter(self):
        from src.rag.retrieval.hybrid import _filter_explicit_document_candidates

        candidates = [
            {"document_number": "49/VBHN-VPQH", "chunk_id": "target"},
            {"document_number": "55/VBHN-VPQH", "chunk_id": "other"},
        ]

        assert _filter_explicit_document_candidates(
            "Van ban 49/VBHN-VPQH quy dinh gi?", candidates
        ) == [candidates[0]]

    def test_split_point_receives_intro_from_same_clause_only(self):
        from src.rag.retrieval.hybrid import _prepend_clause_intros

        point = {
            "chunk_id": "point-h",
            "doc_id": "doc-1",
            "article_num": 6,
            "clause_num": 5,
            "point_num": "h",
            "text_content": "h) Dùng tay cầm và sử dụng điện thoại.",
        }
        parent = {
            "doc_id": "doc-1",
            "article_num": 6,
            "clause_num": 5,
            "text_content": "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng.",
        }

        result = _prepend_clause_intros([point], [parent])

        assert result[0]["text_content"].startswith("Phạt tiền từ 4.000.000 đồng")
        assert "h) Dùng tay cầm" in result[0]["text_content"]

    def test_candidate_uses_heading_path_when_section_path_is_empty(self):
        from src.rag.retrieval.hybrid import _row_to_candidate

        row = SimpleNamespace(
            chunk_id="c1",
            doc_id="d1",
            text_content="Nội dung",
            chunk_type="khoan",
            article_num=7,
            clause_num=1,
            point_num=None,
            status="active",
            effective_date=date(2026, 1, 1),
            canonical_provision_id=None,
            locator_type=None,
            locator_label=None,
            section_path=[],
            metadata_json={"heading_path": ["Điều 7: Xe mô tô, xe gắn máy"]},
            section_number=None,
            sign_codes=[],
            asset_ids=[],
            corpus="road_law",
            doc_title="NĐ 168",
            doc_type="NGHI_DINH",
            legal_status="active",
            source_url=None,
            domain_tags=[],
            document_number="168/2024/NĐ-CP",
        )

        candidate = _row_to_candidate(row, "fts_score", 0.8)

        assert candidate["section_path"] == ["Điều 7: Xe mô tô, xe gắn máy"]

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_runs_db_branches_sequentially(self, monkeypatch):
        from src.rag.retrieval import hybrid as hybrid_module

        active = 0
        max_active = 0
        calls: list[str] = []

        async def branch(name: str, *_args, **_kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            calls.append(name)
            await asyncio.sleep(0)
            active -= 1
            return []

        monkeypatch.setattr(
            hybrid_module,
            "_exact_search",
            lambda *args, **kwargs: branch("exact", *args, **kwargs),
        )
        monkeypatch.setattr(
            hybrid_module,
            "_vector_search",
            lambda *args, **kwargs: branch("vector", *args, **kwargs),
        )
        monkeypatch.setattr(
            hybrid_module,
            "_fts_search",
            lambda *args, **kwargs: branch("fts", *args, **kwargs),
        )

        result = await hybrid_module.hybrid_retrieve(
            session=SimpleNamespace(),
            query="Thong tu 54/2019 noi ve gi?",
            query_embedding=[0.0],
        )

        assert result == []
        assert calls == ["exact", "vector", "fts"]
        assert max_active == 1

    @pytest.mark.asyncio
    async def test_fts_search_binds_corpora_as_postgresql_array(self):
        from src.rag.retrieval.hybrid import _fts_search

        result = SimpleNamespace(all=lambda: [])
        session = SimpleNamespace(execute=AsyncMock(return_value=result))

        assert await _fts_search(session, "vượt đèn đỏ", 5) == []

        statement = session.execute.await_args.args[0]
        assert isinstance(statement._bindparams["corpora"].type, ARRAY)
        assert "websearch_to_tsquery" in str(statement)
        assert "dc.asset_ids" in str(statement)

    def test_fts_query_builder_removes_tsquery_operators(self):
        from src.rag.retrieval.hybrid import _build_tsquery_string

        query = _build_tsquery_string("đèn đỏ') OR NOT |:* & <script>\x00")

        assert "'" not in query
        assert ":*" not in query
        assert "&" not in query
        assert query == '"đèn" OR "đỏ" OR "or" OR "not" OR "script"'

    def test_fts_query_builder_deduplicates_and_caps_terms(self, monkeypatch):
        from src.rag.retrieval import hybrid as hybrid_module

        monkeypatch.setattr(hybrid_module.settings, "RETRIEVAL_FTS_MAX_TERMS", 3)

        query = hybrid_module._build_tsquery_string("alpha beta alpha gamma delta")

        assert query == '"alpha" OR "beta" OR "gamma"'

    def test_merge_deduplicates_by_chunk_id(self):
        from src.rag.retrieval.hybrid import _merge_candidates

        vec = [{"chunk_id": "c1", "vector_score": 0.9, "fts_score": 0.0, "doc_type": "LUAT"}]
        fts = [{"chunk_id": "c1", "vector_score": 0.0, "fts_score": 0.8, "doc_type": "LUAT"}]

        merged = _merge_candidates(vec, fts, "test query", 60)
        assert len(merged) == 1
        assert merged[0]["fts_score"] == 0.8
        assert merged[0]["vector_score"] == 0.9

    def test_merge_respects_top_k(self):
        from src.rag.retrieval.hybrid import _merge_candidates

        vec = [
            {"chunk_id": f"c{i}", "vector_score": 0.5, "fts_score": 0.0, "doc_type": "LUAT"}
            for i in range(40)
        ]
        fts = [
            {"chunk_id": f"f{i}", "vector_score": 0.0, "fts_score": 0.5, "doc_type": "LUAT"}
            for i in range(40)
        ]

        merged = _merge_candidates(vec, fts, "query", 10)
        assert len(merged) == 10

    def test_hybrid_score_formula(self):
        from src.rag.retrieval.hybrid import _compute_hybrid_score

        candidate = {"vector_score": 1.0, "fts_score": 1.0, "doc_type": "LUAT"}
        score = _compute_hybrid_score(candidate, "query")
        assert score == pytest.approx(0.65 + 0.35 + 0.05, abs=0.01)

    def test_rrf_rewards_results_present_in_multiple_branches(self):
        from src.rag.retrieval.hybrid import _merge_candidates

        common = {"chunk_id": "common", "doc_id": "d1", "text_content": "nội dung chung"}
        vector = [common, {"chunk_id": "vector", "doc_id": "d2", "text_content": "vector"}]
        fts = [common, {"chunk_id": "fts", "doc_id": "d3", "text_content": "fts"}]
        merged = _merge_candidates(vector, fts, "query", 10)
        assert merged[0]["chunk_id"] == "common"

    def test_route_qcvn_query_to_technical_corpus(self):
        from src.rag.retrieval.hybrid import route_corpora

        assert route_corpora("Biển P.102 trông như thế nào?") == ("road_technical",)

    def test_route_explicit_document_lookup_to_all_legal_corpora(self):
        from src.rag.retrieval.hybrid import route_corpora

        assert route_corpora("Cho toi thong tin ve thong tu 54/2019/TT-BGTVT") == (
            "road_law",
            "cross_domain_selected",
            "road_technical",
        )

    @pytest.mark.parametrize(
        "query",
        [
            "Thong tu 54/2019 noi ve gi?",
            "Th\u00f4ng t\u01b0 54/2019 n\u00f3i v\u1ec1 g\u00ec?",
            "TT 54/2019 con hieu luc khong?",
            "QCVN 41:2019/BGTVT quy dinh bien bao nao?",
        ],
    )
    def test_route_document_lookup_variants_to_all_legal_corpora(self, query):
        from src.rag.retrieval.hybrid import route_corpora

        assert route_corpora(query) == (
            "road_law",
            "cross_domain_selected",
            "road_technical",
        )

    def test_article_boost_applies(self):
        from src.rag.retrieval.hybrid import _compute_hybrid_score

        candidate = {
            "vector_score": 0.8,
            "fts_score": 0.6,
            "doc_type": "NGHI_DINH",
            "article_num": 9,
        }
        score_with = _compute_hybrid_score(candidate, "điều 9 về mức phạt")
        score_without = _compute_hybrid_score(candidate, "mức phạt chung")
        assert score_with > score_without

    def test_doc_number_boost(self):
        """Query mentioning document number gets +0.15 boost."""
        from src.rag.retrieval.hybrid import _compute_hybrid_score

        candidate = {
            "vector_score": 0.5,
            "fts_score": 0.5,
            "doc_type": "NGHI_DINH",
            "doc_title": "Nghị định 168/2024/NĐ-CP về xử phạt",
        }
        score_with = _compute_hybrid_score(candidate, "NĐ 168/2024 quy định gì")
        score_without = _compute_hybrid_score(candidate, "quy định xử phạt")
        assert score_with - score_without == pytest.approx(0.15, abs=0.01)

    def test_domain_tag_boost(self):
        """Query matching a domain tag gets +0.05 boost."""
        from src.rag.retrieval.hybrid import _compute_hybrid_score

        candidate = {
            "vector_score": 0.5,
            "fts_score": 0.5,
            "doc_type": "NGHI_DINH",
            "domain_tags": ["vận tải hành khách", "xe khách"],
        }
        score_with = _compute_hybrid_score(candidate, "quy định vận tải hành khách")
        score_without = _compute_hybrid_score(candidate, "quy định chung")
        assert score_with - score_without == pytest.approx(0.05, abs=0.01)


# --------------------------------------------------------------------------- #
# Context packer
# --------------------------------------------------------------------------- #
class TestContextPacker:
    def _make_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        article_num: int | None = 1,
    ) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            doc_title="NĐ 100",
            chunk_type="dieu",
            article_num=article_num,
            status="active",
            effective_date=date(2026, 1, 1),
            text_snippet="Nội dung chunk",
            rerank_score=0.9,
        )

    def test_respects_max_chunks(self):
        from src.rag.retrieval.context_packer import pack_context

        chunks = [self._make_chunk(f"c{i}", "d1", article_num=i) for i in range(20)]
        packed = pack_context(chunks, max_chunks=6)
        assert len(packed) == 6

    def test_diversity_constraint(self):
        from src.rag.retrieval.context_packer import pack_context

        chunks = [self._make_chunk(f"c{i}", "d1", article_num=5) for i in range(10)]
        packed = pack_context(chunks, max_chunks=8, max_per_article=3)
        assert len(packed) == 3

    def test_token_budget_caps_packing(self):
        """Token budget should reject chunks once cumulative size exceeds limit."""
        from src.rag.retrieval.context_packer import pack_context

        big_text = "x " * 500
        chunks = []
        for i in range(20):
            c = self._make_chunk(f"c{i}", "d1", article_num=i)
            chunks.append(c.model_copy(update={"text_snippet": big_text}))
        # Budget allows ~3 chunks; should never reach the 20-chunk limit.
        packed = pack_context(chunks, max_chunks=20, token_budget=1000)
        assert 1 <= len(packed) < 20

    def test_format_context_block(self):
        from src.rag.retrieval.context_packer import format_context_block

        chunk = self._make_chunk("abc-123", "d1", article_num=9)
        chunk = chunk.model_copy(
            update={
                "clause_num": 2,
                "point_num": "a",
                "section_path": ["Điều 9: Xử phạt người điều khiển xe mô tô"],
            }
        )
        block = format_context_block(chunk)
        assert "[SOURCE chunk_id=abc-123]" in block
        assert "DOCUMENT:" in block
        assert "STATUS: active" in block
        assert "LOCATOR:" in block
        assert "CONTENT:" in block
        assert "Điều 9" in block
        assert "Khoản 2" in block
        assert "Điểm a" in block
        assert "Xử phạt người điều khiển xe mô tô" in block
