"""In-memory sliding-window rate limiter."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from .interfaces import Clock


class SlidingWindowLimiter:
    """Sliding-window log limiter. Not thread-safe; key count is unbounded.

    A timestamp ``t`` is outside the window when ``t <= now - window`` (exclusive
    boundary, same convention as token expiry). Denied hits are not recorded.
    """

    def __init__(self, clock: Clock, limit: int, window: timedelta) -> None:
        self._clock = clock
        self._limit = limit
        self._window = window
        self._hits: dict[str, deque[datetime]] = {}

    def _prune(self, key: str, now: datetime) -> deque[datetime] | None:
        q = self._hits.get(key)
        if q is None:
            return None
        cutoff = now - self._window
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            del self._hits[key]
            return None
        return q

    def is_blocked(self, key: str) -> bool:
        q = self._prune(key, self._clock.now())
        return q is not None and len(q) >= self._limit

    def record(self, key: str) -> None:
        now = self._clock.now()
        self._prune(key, now)
        self._hits.setdefault(key, deque()).append(now)

    def hit(self, key: str) -> bool:
        """Record and return True if not blocked; otherwise False, unrecorded."""
        if self.is_blocked(key):
            return False
        self.record(key)
        return True
