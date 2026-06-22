"""LangGraph state machine for the Legal RAG agent (spec 09, 13; plan sect6).

The graph implements the full pipeline:
  parse_query -> scope_classify -> {
      deflect |
      hybrid_retrieve -> rerank -> llm_generate -> verify_citation -> inject_disclaimer
  }

scope_classify uses ``Command(goto=...)`` for routing so the graph uses
simple static edges for the main flow and lets the node's return value
handle conditional branching.
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.rag.agent.nodes import (
    deflect,
    hybrid_retrieve_node,
    inject_disclaimer,
    llm_generate,
    output_guardrail_node,
    parse_query,
    rerank_node,
    scope_classify,
    verify_citation_node,
)
from src.rag.agent.state import AgentState

logger = logging.getLogger(__name__)


def build_agent() -> StateGraph:
    """Build and compile the RAG agent graph with in-memory checkpointing.

    Routing:
    - scope_classify returns Command(goto="deflect") for out-of-scope
    - scope_classify returns Command(goto="hybrid_retrieve") for in-scope
    """
    builder = StateGraph(AgentState)

    # ---- Add nodes ----
    builder.add_node("parse_query", parse_query)
    builder.add_node("scope_classify", scope_classify)
    builder.add_node("deflect", deflect)
    builder.add_node("hybrid_retrieve", hybrid_retrieve_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("llm_generate", llm_generate)
    builder.add_node("verify_citation", verify_citation_node)
    builder.add_node("output_guardrail", output_guardrail_node)
    builder.add_node("inject_disclaimer", inject_disclaimer)

    # ---- Edges ----
    # START -> parse -> scope
    builder.add_edge(START, "parse_query")
    builder.add_edge("parse_query", "scope_classify")

    # scope_classify uses Command(goto=...) which adds implicit edges.
    # We only need static edges for nodes that don't self-route.
    builder.add_edge("deflect", END)
    builder.add_edge("hybrid_retrieve", "rerank")
    builder.add_edge("rerank", "llm_generate")
    builder.add_edge("llm_generate", "verify_citation")
    builder.add_edge("verify_citation", "output_guardrail")
    builder.add_edge("output_guardrail", "inject_disclaimer")
    builder.add_edge("inject_disclaimer", END)

    # ---- Compile ----
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


__all__ = ["build_agent"]
