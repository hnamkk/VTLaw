"""Dataset loader for golden JSONL files (spec 14 section 8)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.schemas import EvalCase

GOLDEN_DIR = Path(__file__).parent / "golden"

_DATASET_FILES = sorted(GOLDEN_DIR.glob("*.jsonl"))


def load_cases(paths: list[Path] | None = None) -> list[EvalCase]:
    """Load all eval cases from the golden JSONL dataset files.

    Parameters
    ----------
    paths:
        Explicit list of JSONL file paths to load. Defaults to all files in
        ``eval/golden/``.
    """
    sources = paths or _DATASET_FILES
    cases: list[EvalCase] = []
    for p in sources:
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                cases.append(
                    EvalCase(
                        case_id=raw.get("case_id", ""),
                        category=raw.get("category", ""),
                        question=raw.get("question", ""),
                        expected_behavior=raw.get("expected_behavior", ""),
                        conversation_context=raw.get("conversation_context", ""),
                        expected_doc_ids=raw.get("expected_doc_ids", []),
                        acceptable_doc_ids=raw.get("acceptable_doc_ids", []),
                        expected_chunk_ids=raw.get("expected_chunk_ids", []),
                        expected_answer_points=raw.get("expected_answer_points", []),
                        tags=raw.get("tags", []),
                        forbidden_doc_ids=raw.get("forbidden_doc_ids", []),
                        accepted_guardrail_reasons=raw.get(
                            "accepted_guardrail_reasons", []
                        ),
                        expected_answer_mode=raw.get("expected_answer_mode"),
                        accepted_answer_modes=raw.get("accepted_answer_modes", []),
                        expected_risk_level=raw.get("expected_risk_level"),
                        accepted_risk_levels=raw.get("accepted_risk_levels", []),
                        min_citations=raw.get("min_citations", 0),
                        min_provision_citations=raw.get("min_provision_citations", 0),
                        min_document_sources=raw.get("min_document_sources", 0),
                        min_historical_references=raw.get(
                            "min_historical_references", 0
                        ),
                        require_clarification_question=raw.get(
                            "require_clarification_question", False
                        ),
                        must_have_no_citations=raw.get("must_have_no_citations", False),
                        must_include_disclaimer=raw.get(
                            "must_include_disclaimer", True
                        ),
                        must_deflect=raw.get("must_deflect", False),
                        notes=raw.get("notes", ""),
                    )
                )
    return cases


def load_by_category(category: str) -> list[EvalCase]:
    """Return all cases matching the given category label."""
    return [c for c in load_cases() if c.category == category]
