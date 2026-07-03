"""PostgreSQL integration coverage for the typed FTS corpus array parameter."""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.rag.retrieval.hybrid import _fts_search


@pytest.mark.asyncio
async def test_fts_search_executes_with_typed_corpora_array():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests.")

    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine) as session:
            result = await _fts_search(
                session,
                "quy định giao thông",
                top_k=1,
                corpora=("road_law", "cross_domain_selected"),
            )
        assert isinstance(result, list)
    finally:
        await engine.dispose()
