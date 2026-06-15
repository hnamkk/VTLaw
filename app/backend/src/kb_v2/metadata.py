"""Canonical metadata values for the document repository workflow."""

from __future__ import annotations

CANONICAL_DOCUMENT_ROLES = {
    "primary",
    "amendment",
    "replacement",
    "guidance",
    "foundation",
    "reference",
    "technical",
}

DOCUMENT_ROLE_ALIASES = {
    "base": "primary",
    "original": "primary",
    "main": "primary",
    "primary": "primary",
    "amending": "amendment",
    "amendment": "amendment",
    "supplement": "amendment",
    "replacement": "replacement",
    "replacing": "replacement",
    "guiding": "guidance",
    "guidance": "guidance",
    "foundation": "foundation",
    "reference": "reference",
    "technical": "technical",
}

DOCUMENT_TYPE_ALIASES = {
    "QUY_CHUAN": "QCVN",
    "QUYCHUAN": "QCVN",
}


def normalize_document_role(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower()
    if not key:
        return None
    return DOCUMENT_ROLE_ALIASES.get(key, key if key in CANONICAL_DOCUMENT_ROLES else key)


def normalize_document_type(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().upper()
    if not key:
        return None
    return DOCUMENT_TYPE_ALIASES.get(key, key)
