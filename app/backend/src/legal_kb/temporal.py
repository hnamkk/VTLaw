from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from src.rag.prompts import LEGAL_DISCLAIMER

_AMBIGUOUS_HISTORICAL_MARKERS = (
    "truoc day",
    "truoc kia",
    "luat cu",
    "quy dinh cu",
)
_TEMPORAL_CLARIFICATION_MARKERS = (
    "chua noi ro moc",
    "khong noi ngay cu the",
    "khong noi ro ngay",
    "nhieu moc",
    "moc sua doi",
    "moc thoi gian",
    "chi hoi truoc day",
    "thang 6 nam 2026",
)
_RELATIVE_HISTORICAL_LOOKUP_MARKERS = (
    "truoc khi quy dinh hien hanh",
    "truoc khi quy dinh moi",
    "truoc khi van ban hien hanh",
    "truoc khi van ban moi",
)
_FUTURE_MARKERS = (
    "sap co hieu luc",
    "se co hieu luc",
    "chua co hieu luc",
)
_DATE_PATTERN = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
)


@dataclass(frozen=True)
class TemporalResolution:
    query_date: date
    needs_clarification: bool = False
    clarification_response: str | None = None
    wants_future_effective: bool = False
    has_explicit_date: bool = False


def resolve_query_date(query: str, *, today: date | None = None) -> TemporalResolution:
    today = today or date.today()
    wants_future_effective = _wants_future_effective(query)

    explicit_dates = _extract_explicit_dates(query)
    if len(explicit_dates) > 1:
        return TemporalResolution(
            query_date=today,
            needs_clarification=True,
            clarification_response=(
                "Toi thay ban dang neu nhieu moc thoi gian khac nhau: "
                f"{', '.join(_format_date_options(explicit_dates))}. "
                "Ban muon toi tra theo moc nao?\n\n"
                f"{LEGAL_DISCLAIMER}"
            ),
            wants_future_effective=wants_future_effective,
            has_explicit_date=True,
        )
    if explicit_dates:
        return TemporalResolution(
            query_date=explicit_dates[0],
            wants_future_effective=wants_future_effective,
            has_explicit_date=True,
        )

    relative_dates = _extract_relative_dates(query, today=today)
    if len(relative_dates) > 1:
        return TemporalResolution(
            query_date=today,
            needs_clarification=True,
            clarification_response=(
                "Toi thay cau hoi dang nhac den nhieu moc thoi gian tuong doi khac nhau. "
                "Ban vui long neu mot ngay cu the, vi du 2024-01-01 hoac 01/01/2024.\n\n"
                f"{LEGAL_DISCLAIMER}"
            ),
            wants_future_effective=wants_future_effective,
            has_explicit_date=True,
        )
    if relative_dates:
        return TemporalResolution(
            query_date=relative_dates[0],
            wants_future_effective=wants_future_effective,
            has_explicit_date=True,
        )

    lowered = _normalize_temporal_text(query)
    if any(marker in lowered for marker in _TEMPORAL_CLARIFICATION_MARKERS) or (
        any(marker in lowered for marker in _AMBIGUOUS_HISTORICAL_MARKERS)
        and not any(marker in lowered for marker in _RELATIVE_HISTORICAL_LOOKUP_MARKERS)
        and any(marker in lowered for marker in _TEMPORAL_CLARIFICATION_MARKERS)
    ):
        return TemporalResolution(
            query_date=today,
            needs_clarification=True,
            clarification_response=(
                "Xin loi, toi can mot moc thoi gian cu the de tra dung quy dinh cua giai doan ban dang hoi. "
                "Ban vui long neu ngay ap dung, vi du 2024-01-01 hoac 01/01/2024.\n\n"
                f"{LEGAL_DISCLAIMER}"
            ),
            wants_future_effective=False,
        )

    return TemporalResolution(
        query_date=today,
        wants_future_effective=wants_future_effective,
    )


def _wants_future_effective(query: str) -> bool:
    lowered = _normalize_temporal_text(query)
    return any(marker in lowered for marker in _FUTURE_MARKERS)


def _normalize_temporal_text(query: str) -> str:
    lowered = query.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_marks).strip()


def _extract_explicit_dates(query: str) -> list[date]:
    parsed_dates: list[date] = []
    seen: set[date] = set()
    for match in _DATE_PATTERN.finditer(query):
        try:
            if match.group(1):
                parsed = date(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
            else:
                parsed = date(
                    int(match.group(6)),
                    int(match.group(5)),
                    int(match.group(4)),
                )
        except ValueError:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        parsed_dates.append(parsed)
    return parsed_dates


def _extract_relative_dates(query: str, *, today: date) -> list[date]:
    lowered = query.casefold()
    dates: list[date] = []
    if "hom qua" in lowered or "hôm qua" in lowered:
        dates.append(today - timedelta(days=1))
    if "ngay mai" in lowered or "ngày mai" in lowered:
        dates.append(today + timedelta(days=1))
    return dates


def _format_date_options(values: list[date]) -> list[str]:
    return [value.strftime("%d/%m/%Y") for value in values]
