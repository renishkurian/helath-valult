"""In-memory WebRTC signaling for Vault Send live-video verify (single worker)."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any


class VideoSignalHub:
    def __init__(self, ttl_sec: float = 600.0, max_per_role: int = 80) -> None:
        self._ttl = ttl_sec
        self._max = max_per_role
        self._lock = Lock()
        # request_id -> role (admin|guest) -> deque of messages
        self._q: dict[str, dict[str, deque]] = defaultdict(lambda: {
            "admin": deque(),
            "guest": deque(),
        })
        self._touched: dict[str, float] = {}

    def _purge(self, request_id: str) -> None:
        now = time.monotonic()
        dead = [rid for rid, t in self._touched.items() if now - t > self._ttl]
        for rid in dead:
            self._q.pop(rid, None)
            self._touched.pop(rid, None)
        self._touched[request_id] = now

    def clear(self, request_id: str) -> None:
        with self._lock:
            self._q.pop(request_id, None)
            self._touched.pop(request_id, None)

    def push(self, request_id: str, for_role: str, message: dict[str, Any]) -> None:
        role = "admin" if for_role == "admin" else "guest"
        with self._lock:
            self._purge(request_id)
            bucket = self._q[request_id][role]
            bucket.append({**message, "ts": time.time()})
            while len(bucket) > self._max:
                bucket.popleft()

    def drain(self, request_id: str, for_role: str) -> list[dict[str, Any]]:
        role = "admin" if for_role == "admin" else "guest"
        with self._lock:
            self._purge(request_id)
            bucket = self._q[request_id][role]
            out = list(bucket)
            bucket.clear()
            return out


video_signal_hub = VideoSignalHub()
