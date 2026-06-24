"""Lightweight in-process notification fanout for active SSE clients."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator


class NotificationBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[asyncio.Queue[dict], None]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._subscribers.add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                self._subscribers.discard(queue)

    async def publish(self, payload: dict) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop stale events for slow clients; they can recover via GET /notifications.
                continue


notification_broker = NotificationBroker()
