"""Limit how often one person, or one address, can call FinLint.

Three reasons, each with its own limit in api/main.py:

- Guessing passwords. A few wrong passwords for one name, then a pause.
- The standards agent. Every question costs one to three Groq calls, and the
  free tier allows 30 a minute for the whole server. Without a limit, one busy
  page would use it up for everybody.
- Uploads. Each one parses a whole workbook, which is the heaviest thing the
  server does.

A sliding window: each key keeps the times of its recent requests, and a new
request is refused while the window already holds the limit. Kept in memory,
which suits FinLint's one container (CLAUDE.md Section 5). The counts reset
when the container restarts, and several containers would each count
separately; a shared store such as Redis would be the next step for that.

Checking and counting happen in one locked step (hit_all). Checking first and
counting after the slow part let a burst of simultaneous requests all pass the
check before any was counted: found in review, 24 password guesses got through
a limit of 5.
"""

import collections
import threading
import time

# How often idle keys are swept out, in calls. Without it, every address or
# name ever seen would stay in memory for the life of the process.
SWEEP_EVERY = 1000


class RateLimiter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, collections.deque] = {}
        self._lock = threading.Lock()
        self._calls = 0
        # The longest window any limit uses. A key with no hit inside it can
        # never affect a decision again, so it is safe to drop.
        self._longest = 0.0

    # --- inside the lock ------------------------------------------------------

    def _recent(self, key: str, window: float, now: float) -> collections.deque | None:
        hits = self._hits.get(key)
        if hits is None:
            return None
        while hits and hits[0] <= now - window:
            hits.popleft()
        return hits

    @staticmethod
    def _wait(hits, limit: int, window: float, now: float) -> float:
        count = len(hits) if hits else 0
        if count < limit:
            return 0.0
        # With a limit of 0 there are no hits to wait out: the whole window.
        if not hits:
            return float(window)
        return max(hits[0] + window - now, 0.1)

    def _sweep(self, now: float) -> None:
        self._calls += 1
        if self._calls % SWEEP_EVERY:
            return
        horizon = now - self._longest
        self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > horizon}

    # --- public -----------------------------------------------------------------

    def hit_all(self, limits: list[tuple[str, int, float]]) -> float:
        """Check every (key, limit, window) and, only if all pass, count one hit on each.

        Returns 0 when counted, or the longest wait in seconds when refused.
        A refused request is not counted, so hammering does not extend the wait.
        """
        with self._lock:
            now = self._clock()
            self._sweep(now)
            wait = 0.0
            for key, limit, window in limits:
                self._longest = max(self._longest, window)
                wait = max(wait, self._wait(self._recent(key, window, now), limit, window, now))
            if wait:
                return wait
            for key, _, _ in limits:
                self._hits.setdefault(key, collections.deque()).append(now)
            return 0.0

    def hit(self, key: str, limit: int, window: float) -> float:
        """Count one request for key. Returns the wait in seconds if over the limit."""
        return self.hit_all([(key, limit, window)])

    def wait_needed(self, key: str, limit: int, window: float) -> float:
        """Seconds until key may act again, or 0. Records nothing, creates nothing."""
        with self._lock:
            now = self._clock()
            return self._wait(self._recent(key, window, now), limit, window, now)

    def undo(self, key: str) -> None:
        """Take back the most recent hit on key, for example after a correct password."""
        with self._lock:
            hits = self._hits.get(key)
            if hits:
                hits.pop()

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def size(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        """Forget everything. For tests."""
        with self._lock:
            self._hits.clear()
            self._calls = 0
