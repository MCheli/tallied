"""In-memory sliding-window rate limiter.

No external dependencies (no Redis).  Uses a per-key list of request
timestamps and prunes entries older than the window on every check.
"""

import time
from collections import defaultdict

from fastapi import HTTPException

from app.config import settings


class RateLimiter:
    """Sliding-window rate limiter backed by an in-memory dict."""

    def __init__(self, requests_per_hour: int | None = None):
        self.requests_per_hour = requests_per_hour or settings.rate_limit_per_hour
        self.window = 3600  # 1 hour in seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    # ── public interface ──────────────────────────────────────────────

    def check(self, key: str) -> None:
        """Record a request and raise 429 if the limit is exceeded."""
        now = time.time()
        window_start = now - self.window

        # Prune timestamps outside the current window
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= self.requests_per_hour:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_hour} requests per hour.",
                headers={"Retry-After": "60"},
            )

        self._requests[key].append(now)

    def get_usage(self, key: str) -> tuple[int, int, int]:
        """Return (limit, remaining, reset_timestamp) for *key*."""
        now = time.time()
        window_start = now - self.window

        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        used = len(self._requests[key])
        remaining = max(0, self.requests_per_hour - used)

        # Reset = when the oldest request in the window expires
        if self._requests[key]:
            reset_ts = int(self._requests[key][0] + self.window)
        else:
            reset_ts = int(now + self.window)

        return self.requests_per_hour, remaining, reset_ts


# Module-level singleton used by dependencies and middleware
rate_limiter = RateLimiter()
