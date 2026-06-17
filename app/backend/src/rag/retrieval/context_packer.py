"""Context packer: selects and formats chunks for the LLM prompt (spec 11 §7).

Rules:
- Max CONTEXT_PACK_SIZE chunks (default 8) from reranked top-12.
- No more than 3 chunks from the same Điều (article).
- Token budget cap (CONTEXT_TOKEN_BUDGET) — char-approximated at ~3 chars/token.
- Preserve chunk_id for citation traceability.
- Include parent heading context (doc_title, article/clause info).
"""

from __future__ import annotations

from collections import Counter

from src.core.config import settings
from src.schemas.rag import RetrievedChunk

# Vietnamese legal text averages 2-4 chars/token under tiktoken cl100k_base.
# Using 2.5 (conservative — overestimates token count so we err toward fitting
# in the LLM context window rather than overflowing it).
_CHARS_PER_TOKEN = 2.5


def _estimate_tokens(chunk: RetrievedChunk) -> int:
    """Approximate token count for a formatted context block."""
    return int(len(format_context_block(chunk)) / _CHARS_PER_TOKEN)


def pack_context(
    chunks: list[RetrievedChunk],
    max_chunks: int | None = None,
    max_per_article: int = 3,
    token_budget: int | None = None,
) -> list[RetrievedChunk]:
    """Select diverse top chunks respecting size + diversity + token constraints."""
    max_chunks = max_chunks or settings.CONTEXT_PACK_SIZE
    token_budget = token_budget or settings.CONTEXT_TOKEN_BUDGET
    article_counts: Counter[tuple[str, int | None]] = Counter()
    selected: list[RetrievedChunk] = []
    used_tokens = 0

    for chunk in chunks:
        if len(selected) >= max_chunks:
            break
        key = (chunk.doc_id, chunk.article_num)
        if article_counts[key] >= max_per_article:
            continue
        chunk_tokens = _estimate_tokens(chunk)
        if used_tokens + chunk_tokens > token_budget:
            # Skip this chunk if it would blow the budget; keep trying smaller ones.
            continue
        article_counts[key] += 1
        used_tokens += chunk_tokens
        selected.append(chunk)

    return selected


def format_context_block(chunk: RetrievedChunk) -> str:
    """Format a single chunk as a context block for the LLM prompt."""
    location_parts: list[str] = []
    if chunk.article_num is not None:
        location_parts.append(f"Điều {chunk.article_num}")
    if chunk.clause_num is not None:
        location_parts.append(f"Khoản {chunk.clause_num}")
    if chunk.point_num is not None:
        location_parts.append(f"Điểm {chunk.point_num}")
    if chunk.locator_label:
        location_parts.append(chunk.locator_label)
    heading_path = " > ".join(chunk.section_path)
    location = ", ".join(location_parts) if location_parts else chunk.chunk_type

    content = chunk.full_text or chunk.text_snippet

    document_label = chunk.document_number or chunk.doc_title
    lines = [
        f"[SOURCE chunk_id={chunk.chunk_id}]",
        f"DOCUMENT: {document_label} | {chunk.doc_title}",
        f"STATUS: {chunk.status} | EFFECTIVE_DATE: {chunk.effective_date}",
        f"LOCATOR: {location}",
    ]
    if heading_path:
        lines.append(heading_path)
    lines.append(f"CONTENT: {content}")
    return "\n".join(lines)


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Format all selected chunks into the context string for the prompt."""
    blocks = [format_context_block(c) for c in chunks]
    return "\n\n---\n\n".join(blocks)
