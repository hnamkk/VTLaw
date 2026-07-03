"""Tests for the embedding client batching/order logic (spec 09 §4).

The OpenAI call is mocked so no network or API key is needed; we assert batch
splitting and that input order is preserved across batches.
"""

from __future__ import annotations

import pytest

from src.rag import embedding


@pytest.fixture
def fake_client(monkeypatch, tmp_path):
    """Replace the cached embedder with a stub returning index-tagged vectors."""
    calls: list[list[str]] = []

    class _Stub:
        async def aembed_documents(self, texts):
            calls.append(list(texts))
            # Return a 1-d vector encoding the text so we can check ordering.
            return [[float(len(t))] for t in texts]

        async def aembed_query(self, text):
            calls.append([text])
            return [float(len(text))]

    monkeypatch.setattr(embedding, "_embedder", _Stub())
    monkeypatch.setattr(embedding, "_embedding_cache", {})
    monkeypatch.setattr(embedding, "_CACHE_PATH", tmp_path / "embedding-cache.sqlite3")
    monkeypatch.setattr(embedding, "_BATCH_SIZE", 2)
    return calls


async def test_embed_texts_empty_returns_empty(fake_client):
    assert await embedding.embed_texts([]) == []
    assert fake_client == []


async def test_embed_texts_batches_and_preserves_order(fake_client):
    texts = ["a", "bb", "ccc", "dddd", "e"]
    vectors = await embedding.embed_texts(texts)
    # 5 texts at batch size 2 -> 3 batches.
    assert len(fake_client) == 3
    assert [len(b) for b in fake_client] == [2, 2, 1]
    # Order preserved: vector value == len(text).
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [1.0]]


async def test_embed_query(fake_client):
    assert await embedding.embed_query("hello") == [5.0]


async def test_embed_query_caps_long_input(fake_client, monkeypatch):
    monkeypatch.setattr(embedding.settings, "QUERY_EMBEDDING_MAX_CHARS", 12)

    assert await embedding.embed_query("alpha beta gamma delta") == [10.0]

    assert fake_client == [["alpha beta"]]
