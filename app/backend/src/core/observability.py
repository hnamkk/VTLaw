"""Optional Langfuse tracing with export-stage PII masking."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from src.core.config import settings

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler
    from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult

logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")


def redact_pii(value: str) -> str:
    value = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", value)
    return _PHONE_PATTERN.sub("[PHONE_REDACTED]", value)


def _mask_otel_spans(*, params: "MaskOtelSpansParams") -> "MaskOtelSpansResult | None":
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches: dict[str, OtelSpanPatch] = {}
    for identifier, span in params.spans.items():
        replacements: dict[str, Any] = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                masked = redact_pii(value)
                if masked != value:
                    replacements[key] = masked
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches) if patches else None


@lru_cache(maxsize=1)
def _initialize_langfuse() -> bool:
    if not (
        settings.LANGFUSE_TRACING_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    ):
        return False
    try:
        from langfuse import Langfuse

        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_BASE_URL,
            environment=settings.APP_ENV.lower(),
            sample_rate=settings.LANGFUSE_SAMPLE_RATE,
            mask_otel_spans=_mask_otel_spans,
        )
        return True
    except Exception:
        logger.warning("Langfuse initialization failed; chat tracing is disabled.", exc_info=True)
        return False


def get_langfuse_callback() -> "CallbackHandler | None":
    """Return a fresh LangChain callback or None when tracing is unavailable."""
    if not _initialize_langfuse():
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception:
        logger.warning("Langfuse callback creation failed.", exc_info=True)
        return None


__all__ = ["get_langfuse_callback", "redact_pii"]
