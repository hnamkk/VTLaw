"""LangGraph RAG agent for Vietnamese legal Q&A.

Exposes ``build_agent()`` which returns a compiled ``StateGraph`` ready for
invoke/stream. The graph implements the full pipeline from parse -> scope ->
retrieve -> rerank -> generate -> verify -> disclaimer.
"""

from __future__ import annotations

from src.rag.agent.graph import build_agent

__all__ = ["build_agent"]
