"""A tiny in-memory sliding-window limiter for public forms (per server process).

It slows down guessing on the report-tracking page. It is deliberately simple: the counters live in memory, so
they reset when the server restarts and each worker process keeps its own counts. That is enough to stop casual
guessing; a production deployment behind several workers would use a shared store (e.g. Redis) instead.
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """Allow ``limit`` recorded events per ``window_seconds`` for each key (for example an IP address)."""

    MAX_KEYS = 5000

    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, hits, now):
        while hits and now - hits[0] > self.window:
            hits.popleft()

    def blocked(self, key):
        """True while ``key`` has used up its allowance."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return False
            self._prune(hits, now)
            if not hits:
                del self._hits[key]
                return False
            return len(hits) >= self.limit

    def hit(self, key):
        """Record one (failed) attempt for ``key``."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            hits.append(now)
            self._prune(hits, now)
            if len(self._hits) > self.MAX_KEYS:  # keep memory bounded
                for other in list(self._hits):
                    queue = self._hits[other]
                    self._prune(queue, now)
                    if not queue:
                        del self._hits[other]

    def reset(self, key=None):
        """Forget ``key`` (or everything) - used by the tests."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


# 8 wrong report-ID / contact combinations per 10 minutes and IP address
track_limiter = SlidingWindowLimiter(limit=8, window_seconds=600)
