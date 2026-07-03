from __future__ import annotations

import json

import pytest

from src.rag.intent import classify_query_intent
from src.rag.policy import is_legal_advice_strategy, is_objective_procedure_request
from src.rag.query_policy import (
    DEFAULT_QUERY_POLICY_PATH,
    clear_query_policy_cache,
    load_query_policy,
    validate_query_policy_startup,
)
from src.rag.retrieval.query_utils import (
    expand_query_for_retrieval,
    semantic_document_scope_numbers,
)


@pytest.fixture(autouse=True)
def _clear_query_policy_cache():
    clear_query_policy_cache()
    yield
    clear_query_policy_cache()


def test_load_query_policy_parses_default_config():
    policy = load_query_policy()

    assert policy.schema_version == 1
    assert policy.version
    assert "tom tat" in policy.intent_hints.summary_phrases
    assert any(rule.name == "transport_business_requirements" for rule in policy.retrieval_expansion.rules)


def test_expand_query_for_retrieval_uses_versioned_rules():
    expanded = expand_query_for_retrieval("Thong tu nay quy dinh nhung van de chinh nao?")

    assert "pham vi dieu chinh" in expanded


def test_semantic_document_scope_separates_two_road_base_laws():
    assert semantic_document_scope_numbers(
        "Luật Đường bộ 2024 tập trung vào hạ tầng và vận tải đường bộ như thế nào?"
    ) == ("35/2024/QH15",)
    assert semantic_document_scope_numbers(
        "Luật Trật tự, an toàn giao thông đường bộ 2024 bao quát quy tắc giao thông nào?"
    ) == ("36/2024/QH15",)
    assert semantic_document_scope_numbers("quy định giao thông đường bộ hiện hành là gì?") == ()


def test_semantic_document_scope_covers_high_signal_unaccented_topics():
    assert semantic_document_scope_numbers("Dan can cu ve tem kiem dinh xe co gioi") == (
        "16/2021/TT-BGTVT",
    )
    assert semantic_document_scope_numbers("Can cu nao quy dinh sat hach mo to hang A1?") == (
        "108/2026/TT-BCA",
    )
    assert semantic_document_scope_numbers("Noi chu xe nop ho so dang ky xe o dau?") == (
        "79/2024/TT-BCA",
    )


def test_semantic_document_scope_routes_multi_document_topics():
    assert semantic_document_scope_numbers(
        "Luat Duong bo 2024 va Luat Trat tu an toan giao thong duong bo 2024 khac nhau o pham vi trong tam nao?"
    ) == ("35/2024/QH15", "36/2024/QH15")
    assert semantic_document_scope_numbers(
        "Dang ky xe va kiem dinh xe xac nhan hai van de khac nhau nhu the nao?"
    ) == ("79/2024/TT-BCA", "16/2021/TT-BGTVT")


def test_classify_query_intent_uses_versioned_intent_hints():
    result = classify_query_intent("tom tat van ban 35/2024/QH15")

    assert result.query_intent == "document_summary_standard"
    assert result.document_number == "35/2024/QH15"


def test_legal_advice_policy_uses_versioned_patterns():
    assert is_legal_advice_strategy("Lam sao tranh bi phat?", "general_legal") is True
    assert is_objective_procedure_request("Toi nen lam gi de dang ky xe?", "procedure") is True


def test_query_policy_loader_rejects_duplicate_values(tmp_path):
    payload = json.loads(DEFAULT_QUERY_POLICY_PATH.read_text(encoding="utf-8"))
    payload["intent_hints"]["summary_phrases"] = ["tom tat", "tom tat"]
    invalid_path = tmp_path / "query_policy.invalid.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicates"):
        load_query_policy(str(invalid_path))


def test_query_policy_startup_validation_rejects_unknown_term_group(tmp_path):
    payload = json.loads(DEFAULT_QUERY_POLICY_PATH.read_text(encoding="utf-8"))
    payload["retrieval_expansion"]["rules"][0]["match_any_group"] = "missing_group"
    invalid_path = tmp_path / "query_policy.unknown-group.json"
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown term groups"):
        validate_query_policy_startup(str(invalid_path))
