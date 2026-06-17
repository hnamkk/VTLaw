"""Versioned query policy loader for deterministic text rules."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _ensure_unique_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if any(not value for value in cleaned):
        raise ValueError(f"{field_name} must not contain empty strings")
    duplicates = sorted({value for value in cleaned if cleaned.count(value) > 1})
    if duplicates:
        raise ValueError(f"{field_name} contains duplicates: {', '.join(duplicates)}")
    return cleaned


class IntentHintsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary_phrases: tuple[str, ...]
    document_lookup_phrases: tuple[str, ...]
    effective_status_phrases: tuple[str, ...]
    comparison_history_phrases: tuple[str, ...]
    definition_phrases: tuple[str, ...]
    obligation_phrases: tuple[str, ...]
    penalty_phrases: tuple[str, ...]
    procedure_phrases: tuple[str, ...]
    ambiguous_phrases: tuple[str, ...]
    ambiguous_short_cues: tuple[str, ...]

    @model_validator(mode="after")
    def validate_lists(self) -> "IntentHintsConfig":
        for field_name in type(self).model_fields:
            _ensure_unique_strings(getattr(self, field_name), field_name=field_name)
        return self


class FollowUpConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    prefixes: tuple[str, ...]
    phrases: tuple[str, ...]
    low_signal_user_intents: tuple[str, ...]
    history_question_blockers: tuple[str, ...]
    topic_hints: tuple[str, ...]
    standalone_topic_hints: tuple[str, ...]

    @model_validator(mode="after")
    def validate_lists(self) -> "FollowUpConfig":
        for field_name in type(self).model_fields:
            _ensure_unique_strings(getattr(self, field_name), field_name=field_name)
        return self


class LegalAdviceConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    procedure_hints: tuple[str, ...]
    objective_checklist_hints: tuple[str, ...]
    strategy_phrases: tuple[str, ...]
    high_risk_strategy_phrases: tuple[str, ...]
    dispute_phrases: tuple[str, ...]

    @model_validator(mode="after")
    def validate_lists(self) -> "LegalAdviceConfig":
        for field_name in type(self).model_fields:
            _ensure_unique_strings(getattr(self, field_name), field_name=field_name)
        return self


class RetrievalExpansionRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    expansion_text: str
    match_any: tuple[str, ...] = ()
    match_any_group: str | None = None
    match_all_group: str | None = None
    requires_any_of: tuple[str, ...] = ()
    requires_all_groups: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_rule(self) -> "RetrievalExpansionRule":
        name = self.name.strip()
        expansion_text = self.expansion_text.strip()
        if not name:
            raise ValueError("retrieval expansion rule name must not be empty")
        if not expansion_text:
            raise ValueError(f"retrieval expansion rule {name} must have expansion_text")
        _ensure_unique_strings(self.match_any, field_name=f"{name}.match_any")
        _ensure_unique_strings(self.requires_any_of, field_name=f"{name}.requires_any_of")
        _ensure_unique_strings(
            self.requires_all_groups,
            field_name=f"{name}.requires_all_groups",
        )
        if not any(
            (
                self.match_any,
                self.match_any_group,
                self.match_all_group,
                self.requires_any_of,
                self.requires_all_groups,
            )
        ):
            raise ValueError(f"retrieval expansion rule {name} has no match conditions")
        return self


class RetrievalExpansionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    term_groups: dict[str, tuple[str, ...]]
    rules: tuple[RetrievalExpansionRule, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_config(self) -> "RetrievalExpansionConfig":
        for group_name, terms in self.term_groups.items():
            _ensure_unique_strings(terms, field_name=f"term_groups.{group_name}")
        rule_names = tuple(rule.name for rule in self.rules)
        _ensure_unique_strings(rule_names, field_name="retrieval_expansion.rules")
        known_groups = set(self.term_groups)
        for rule in self.rules:
            referenced_groups = {
                group_name
                for group_name in (
                    rule.match_any_group,
                    rule.match_all_group,
                )
                if group_name is not None
            }
            referenced_groups.update(rule.requires_any_of)
            referenced_groups.update(
                part
                for item in rule.requires_all_groups
                for part in item.split("|")
                if part
            )
            missing = sorted(referenced_groups - known_groups)
            if missing:
                raise ValueError(
                    f"retrieval expansion rule {rule.name} references unknown term groups: "
                    + ", ".join(missing)
                )
        return self


class QueryPolicyConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int
    version: str
    intent_hints: IntentHintsConfig
    follow_up: FollowUpConfig
    legal_advice: LegalAdviceConfig
    retrieval_expansion: RetrievalExpansionConfig

    @model_validator(mode="after")
    def validate_schema(self) -> "QueryPolicyConfig":
        if self.schema_version != 1:
            raise ValueError(f"Unsupported query policy schema_version: {self.schema_version}")
        if not self.version.strip():
            raise ValueError("query policy version must not be empty")
        return self


DEFAULT_QUERY_POLICY_PATH = Path(__file__).resolve().parent / "policies" / "query_policy.json"


def _load_query_policy_from_path(path: Path) -> QueryPolicyConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Query policy file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Query policy JSON is invalid at {path}: {exc}") from exc

    try:
        return QueryPolicyConfig.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"Query policy validation failed for {path}: {exc}") from exc


@lru_cache(maxsize=4)
def load_query_policy(path: str | None = None) -> QueryPolicyConfig:
    resolved = Path(path) if path is not None else DEFAULT_QUERY_POLICY_PATH
    return _load_query_policy_from_path(resolved)


def get_query_policy() -> QueryPolicyConfig:
    return load_query_policy()


def validate_query_policy_startup(path: str | None = None) -> QueryPolicyConfig:
    return load_query_policy(path)


def clear_query_policy_cache() -> None:
    load_query_policy.cache_clear()


__all__ = [
    "DEFAULT_QUERY_POLICY_PATH",
    "QueryPolicyConfig",
    "clear_query_policy_cache",
    "get_query_policy",
    "load_query_policy",
    "validate_query_policy_startup",
]
