"""Tests for the RAG agent graph structure (Phase 6).

Covers: state schema, graph topology, out-of-scope routing,
and the build_agent function. No DB or LLM calls.
"""

from __future__ import annotations

from src.rag.agent.graph import build_agent
from src.rag.agent.state import AgentState


# --------------------------------------------------------------------------- #
# State schema
# --------------------------------------------------------------------------- #
def test_agent_state_keys():
    """Verify all expected keys exist in AgentState."""
    keys = set(AgentState.__annotations__.keys())
    expected = {
        "query",
        "normalized_query",
        "retrieval_query",
        "query_intent",
        "query_document_number",
        "query_date",
        "query_has_explicit_date",
        "conversation_context",
        "follow_up_used",
        "follow_up_confidence",
        "follow_up_reason",
        "scope_result",
        "status_filter",
        "retrieved_contexts",
        "reranker_failed",
        "reranker_used",
        "reranker_error_code",
        "low_confidence",
        "retrieval_candidate_count",
        "rerank_top_score",
        "llm_output",
        "repealed_notice",
        "temporal_notice",
        "evidence_policy_notice",
        "evidence_notice",
        "response_document_sources",
        "response_historical_references",
        "verified_citations",
        "faithfulness_score",
        "has_hallucination",
        "disclaimer_appended",
        "guardrail_triggered",
        "guardrail_stage",
        "guardrail_reason",
        "final_response",
        "is_out_of_scope",
        "injection_detected",
        "kb_version",
    }
    assert keys == expected, f"Missing: {expected - keys}, Extra: {keys - expected}"


# --------------------------------------------------------------------------- #
# Compiled graph
# --------------------------------------------------------------------------- #
def test_build_agent_returns_compiled_graph():
    graph = build_agent()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")
    assert graph.checkpointer is not None


def test_graph_has_all_nodes():
    graph = build_agent()
    node_names = set(graph.nodes)
    expected = {
        "__start__",
        "parse_query",
        "scope_classify",
        "deflect",
        "hybrid_retrieve",
        "rerank",
        "llm_generate",
        "verify_citation",
        "output_guardrail",
        "inject_disclaimer",
    }
    missing = expected - node_names
    extra = node_names - expected
    assert not missing, f"Missing nodes: {missing}"
    assert not extra, f"Unexpected nodes: {extra}"


def test_graph_has_parse_query_node():
    graph = build_agent()
    assert "parse_query" in graph.nodes


def test_graph_has_scope_classify_node():
    graph = build_agent()
    assert "scope_classify" in graph.nodes


def test_graph_has_deflect_node():
    graph = build_agent()
    assert "deflect" in graph.nodes


def test_graph_has_hybrid_retrieve_node():
    graph = build_agent()
    assert "hybrid_retrieve" in graph.nodes


def test_graph_has_rerank_node():
    graph = build_agent()
    assert "rerank" in graph.nodes


def test_graph_has_llm_generate_node():
    graph = build_agent()
    assert "llm_generate" in graph.nodes


def test_graph_has_verify_citation_node():
    graph = build_agent()
    assert "verify_citation" in graph.nodes


def test_graph_has_inject_disclaimer_node():
    graph = build_agent()
    assert "inject_disclaimer" in graph.nodes


def test_graph_has_output_guardrail_node():
    graph = build_agent()
    assert "output_guardrail" in graph.nodes


def test_graph_has_checkpointer():
    graph = build_agent()
    assert graph.checkpointer is not None
