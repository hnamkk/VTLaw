"""Retrieval helpers exposed to the current KB runtime.

The active runtime uses ``hybrid_legal`` directly. Legacy ``hybrid`` stays in its
own module for maintenance and targeted tests only.
"""

from src.rag.retrieval.context_packer import format_context, pack_context
from src.rag.retrieval.query_utils import expand_query_for_retrieval, query_for_local_ranking
from src.rag.retrieval.scope import classify_scope

__all__ = [
    "classify_scope",
    "expand_query_for_retrieval",
    "format_context",
    "pack_context",
    "query_for_local_ranking",
]
