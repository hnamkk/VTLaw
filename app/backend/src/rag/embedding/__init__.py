"""OpenAI embeddings with bounded batches and a hash-keyed SQLite cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import settings

_BATCH_SIZE = 64
_embedder: OpenAIEmbeddings | None = None
_CACHE_PATH = Path(__file__).resolve().parents[3] / "storage" / "embedding_cache.sqlite3"
_embedding_cache: dict[str, list[float]] = {}


def _cache_key(text: str) -> str:
    payload = f"{settings.EMBEDDING_MODEL_NAME}:{settings.EMBEDDING_DIM}:{text}".encode()
    return hashlib.sha256(payload).hexdigest()


def _connect() -> sqlite3.Connection:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_CACHE_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_cache (
            cache_key TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def _cache_get(texts: list[str]) -> dict[int, list[float]]:
    found: dict[int, list[float]] = {}
    keys = [_cache_key(text) for text in texts]
    missing_keys: list[str] = []
    for index, key in enumerate(keys):
        if key in _embedding_cache:
            found[index] = _embedding_cache[key]
        else:
            missing_keys.append(key)
    if not missing_keys:
        return found
    rows: list[tuple[str, str]] = []
    with _connect() as connection:
        for start in range(0, len(missing_keys), 500):
            batch = missing_keys[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows.extend(
                connection.execute(
                    "SELECT cache_key, vector_json FROM embedding_cache "
                    f"WHERE cache_key IN ({placeholders})",
                    batch,
                ).fetchall()
            )
    vectors = {key: json.loads(value) for key, value in rows}
    for index, key in enumerate(keys):
        if index not in found and key in vectors:
            _embedding_cache[key] = vectors[key]
            found[index] = vectors[key]
    return found


def _cache_put(items: list[tuple[str, list[float]]]) -> None:
    if not items:
        return
    rows = []
    for text, vector in items:
        key = _cache_key(text)
        _embedding_cache[key] = vector
        rows.append(
            (
                key,
                settings.EMBEDDING_MODEL_NAME,
                settings.EMBEDDING_DIM,
                json.dumps(vector, separators=(",", ":")),
            )
        )
    with _connect() as connection:
        connection.executemany(
            """
            INSERT INTO embedding_cache(cache_key, model, dimensions, vector_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                model=excluded.model,
                dimensions=excluded.dimensions,
                vector_json=excluded.vector_json
            """,
            rows,
        )


def _client() -> OpenAIEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL_NAME,
            api_key=settings.OPENAI_API_KEY,
            dimensions=settings.EMBEDDING_DIM,
        )
    return _embedder


def prepare_query_for_embedding(text: str) -> str:
    """Bound query embeddings consistently for chat, tools, and internal jobs."""
    normalized = " ".join(text.split())
    max_chars = max(1, settings.QUERY_EMBEDDING_MAX_CHARS)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rsplit(" ", 1)[0] or normalized[:max_chars]


_retry = retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    reraise=True,
)


@_retry
async def _embed_batch(texts: list[str]) -> list[list[float]]:
    return await _client().aembed_documents(texts)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    cached = _cache_get(texts)
    results: list[list[float] | None] = [cached.get(index) for index in range(len(texts))]
    missing_indices = [index for index, vector in enumerate(results) if vector is None]
    new_items: list[tuple[str, list[float]]] = []
    for start in range(0, len(missing_indices), _BATCH_SIZE):
        batch_indices = missing_indices[start : start + _BATCH_SIZE]
        batch_texts = [texts[index] for index in batch_indices]
        vectors = await _embed_batch(batch_texts)
        for index, text, vector in zip(batch_indices, batch_texts, vectors, strict=True):
            results[index] = vector
            new_items.append((text, vector))
    _cache_put(new_items)
    return [vector for vector in results if vector is not None]


async def embed_query(text: str) -> list[float]:
    prepared = prepare_query_for_embedding(text)
    cached = _cache_get([prepared])
    if 0 in cached:
        return cached[0]
    vector = await _client().aembed_query(prepared)
    _cache_put([(prepared, vector)])
    return vector


__all__ = ["embed_texts", "embed_query", "prepare_query_for_embedding"]
