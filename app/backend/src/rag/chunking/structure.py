"""Detect Vietnamese legal structure markers in parsed text lines (spec 10 §4).

Recognizes the four-level hierarchy:
    Chương <roman> : <title>     e.g. "Chương II QUY ĐỊNH CHUNG"
    Điều <n>. <title>            e.g. "Điều 9. Điều kiện của người lái xe"
    <n>. <clause text>           e.g. "1. Người lái xe phải..."   (Khoản)
    <letter>) <point text>       e.g. "a) Có giấy phép..."        (Điểm)

Roman numerals are converted to ints for ``chapter_num``. Clause/point markers
are deliberately matched at line start only; mid-sentence "1." or "a)" inside a
paragraph won't false-trigger because parser blocks are already line-split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_CHUONG_RE = re.compile(r"^\s*Chương\s+([IVXLCDM]+)\b[.:]?\s*(.*)$", re.IGNORECASE)
_DIEU_RE = re.compile(r"^\s*Điều\s+(\d+)\s*[.:]?\s*(.*)$", re.IGNORECASE)
# Khoản: "1." or "1)" at line start, followed by content.
_KHOAN_RE = re.compile(r"^\s*(\d+)\s*[.)]\s+(.*)$")
# Điểm: "a)" / "đ)" — single Vietnamese letter then ')'.
_DIEM_RE = re.compile(r"^\s*([a-zđ])\s*\)\s+(.*)$", re.IGNORECASE)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int | None:
    s = s.upper()
    if not s or any(c not in _ROMAN for c in s):
        return None
    total = 0
    prev = 0
    for c in reversed(s):
        val = _ROMAN[c]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


class MarkerKind(str, Enum):
    chuong = "chuong"
    dieu = "dieu"
    khoan = "khoan"
    diem = "diem"
    body = "body"  # plain continuation text


@dataclass
class Marker:
    """A classified line: its structural role plus parsed number and remainder."""

    kind: MarkerKind
    number: int | None  # chapter/article/clause number; None for body
    point: str | None  # point letter, only for diem
    title: str  # heading title or clause/point body text


def classify_line(line: str) -> Marker:
    """Classify a single cleaned line into a structural marker.

    Order matters: Chương and Điều are checked before the generic numbered
    Khoản pattern so "Điều 9." is not mistaken for a clause.
    """
    m = _CHUONG_RE.match(line)
    if m:
        return Marker(MarkerKind.chuong, roman_to_int(m.group(1)), None, m.group(2).strip())

    m = _DIEU_RE.match(line)
    if m:
        return Marker(MarkerKind.dieu, int(m.group(1)), None, m.group(2).strip())

    m = _KHOAN_RE.match(line)
    if m:
        return Marker(MarkerKind.khoan, int(m.group(1)), None, m.group(2).strip())

    m = _DIEM_RE.match(line)
    if m:
        return Marker(MarkerKind.diem, None, m.group(1).lower(), m.group(2).strip())

    return Marker(MarkerKind.body, None, None, line.strip())
