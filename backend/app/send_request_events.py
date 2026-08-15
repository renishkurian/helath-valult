"""In-process fan-out for Vault Send access-request SSE (single uvicorn worker)."""
from __future__ import annotations

import asyncio
from typing import Any


class SendRequestHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, owner_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subs.setdefault(owner_id, set()).add(q)
        return q

    async def unsubscribe(self, owner_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            bucket = self._subs.get(owner_id)
            if not bucket:
                return
            bucket.discard(q)
            if not bucket:
                self._subs.pop(owner_id, None)

    def publish(self, owner_id: str, payload: dict[str, Any]) -> None:
        """Wake all admin tabs for this owner. Safe to call from sync request handlers."""
        for q in list(self._subs.get(owner_id) or ()):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass


send_request_hub = SendRequestHub()
