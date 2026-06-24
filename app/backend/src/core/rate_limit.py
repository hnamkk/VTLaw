"""Small sliding-window rate limiter for public chat traffic."""

from __future__ import annotations

import time
from asyncio import Lock
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0
    limit: int = 0
    window_seconds: int = 0


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0 or window_seconds <= 0:
            return RateLimitResult(allowed=True)

        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                return RateLimitResult(
                    allowed=False,
                    retry_after_seconds=retry_after,
                    limit=limit,
                    window_seconds=window_seconds,
                )

            hits.append(now)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                window_seconds=window_seconds,
            )

    async def check_many(self, limits: list[tuple[str, int, int]]) -> RateLimitResult:
        """Check several windows and record the hit only if every window allows it."""
        active_limits = [
            (key, limit, window_seconds)
            for key, limit, window_seconds in limits
            if limit > 0 and window_seconds > 0
        ]
        if not active_limits:
            return RateLimitResult(allowed=True)

        now = time.monotonic()
        async with self._lock:
            for key, _limit, window_seconds in active_limits:
                cutoff = now - window_seconds
                hits = self._hits[key]
                while hits and hits[0] <= cutoff:
                    hits.popleft()

            for key, limit, window_seconds in active_limits:
                hits = self._hits[key]
                if len(hits) >= limit:
                    retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                    return RateLimitResult(
                        allowed=False,
                        retry_after_seconds=retry_after,
                        limit=limit,
                        window_seconds=window_seconds,
                    )

            for key, _limit, _window_seconds in active_limits:
                self._hits[key].append(now)

        strictest = min(active_limits, key=lambda item: item[1])
        return RateLimitResult(
            allowed=True,
            limit=strictest[1],
            window_seconds=strictest[2],
        )


public_chat_rate_limiter = SlidingWindowRateLimiter()
