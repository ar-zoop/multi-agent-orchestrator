"""Per-client rate limiting for the public demo.

In-process sliding window, no Redis. The deployment is a single container, so a
shared store would be state for its own sake; if this ever runs on more than one
instance the `RateLimiter` interface is the seam to swap.
"""

import os
import threading
import time
from collections import defaultdict, deque

DEFAULT_MAX_REQUESTS = 10
DEFAULT_WINDOW_SECONDS = 60.0

# Only endpoints that can reach a provider are metered. /health stays free so
# platform health checks are never rate limited.
METERED_PATHS = ("/run", "/stream", "/agents/sql", "/agents/review", "/agents/run")


class RateLimiter:
    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock=time.monotonic,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, **kwargs) -> "RateLimiter":
        return cls(
            max_requests=int(os.getenv("RATE_LIMIT_REQUESTS", DEFAULT_MAX_REQUESTS)),
            window_seconds=float(
                os.getenv("RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS)
            ),
            **kwargs,
        )

    def check(self, key: str) -> float | None:
        """Record a hit for `key`. Returns `None` if allowed, else seconds to wait."""
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return max(0.0, hits[0] + self.window_seconds - now)
            hits.append(now)
            return None

    def remaining(self, key: str) -> int:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            return max(0, self.max_requests - len(hits))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def is_metered(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in METERED_PATHS)


def client_key(request) -> str:
    """The caller's IP, honouring the first hop of X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def required_api_key() -> str | None:
    """Set `API_KEY` to close the demo off entirely; unset leaves it open but limited."""
    return os.getenv("API_KEY") or None
