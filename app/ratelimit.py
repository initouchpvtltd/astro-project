"""Request rate limiting.

Two separate concerns:

- Per-client limits stop one caller monopolising the service. The scan in
  milestone 3 is processor heavy, so this matters more later than it does now.
- A global ceiling on GeoNames calls protects the account quota, which is a
  shared resource a distributed flood could exhaust even under per-client
  limits.

Counters live in process memory. The service runs as a single instance, so
that is sufficient; moving to several instances would need shared storage.
"""

import os
import threading
import time
from collections import deque


def _int_env(name, default):
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


# Per client, per endpoint group.
CITIES_PER_MINUTE = _int_env("RATE_LIMIT_CITIES_PER_MINUTE", 20)
CHART_PER_MINUTE = _int_env("RATE_LIMIT_CHART_PER_MINUTE", 60)

# Across every client, protecting the GeoNames daily allowance.
GEONAMES_PER_HOUR = _int_env("GEONAMES_MAX_PER_HOUR", 500)

# Clients idle longer than this are forgotten, so memory does not grow with
# every address that ever called.
_IDLE_EVICTION_SECONDS = 600


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds, message):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after_seconds))
        self.message = message


class SlidingWindow:
    """Counts events in the trailing window, which is fairer than fixed buckets.

    A fixed bucket lets a caller spend the whole allowance at the end of one
    window and again at the start of the next.
    """

    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self._events = {}
        self._lock = threading.Lock()

    def check(self, key, now=None):
        if self.limit <= 0:  # 0 disables the limit
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            self._evict(now)
            stamps = self._events.setdefault(key, deque())
            cutoff = now - self.window
            while stamps and stamps[0] <= cutoff:
                stamps.popleft()
            if len(stamps) >= self.limit:
                retry_after = stamps[0] + self.window - now
                raise RateLimitExceeded(
                    retry_after,
                    f"Rate limit reached: {self.limit} requests per "
                    f"{self.window} seconds. Try again shortly.",
                )
            stamps.append(now)

    def _evict(self, now):
        stale = now - self.window - _IDLE_EVICTION_SECONDS
        for key in [k for k, v in self._events.items() if not v or v[-1] <= stale]:
            del self._events[key]

    def reset(self):
        with self._lock:
            self._events.clear()


cities_limiter = SlidingWindow(CITIES_PER_MINUTE, 60)
chart_limiter = SlidingWindow(CHART_PER_MINUTE, 60)
geonames_budget = SlidingWindow(GEONAMES_PER_HOUR, 3600)


def client_key(request):
    """Identify the caller.

    Render terminates TLS at its own proxy, so the socket address is always
    the proxy. X-Forwarded-For carries the original client as the first entry.
    It can be spoofed, which is why this guards a quota rather than anything
    that needs to be trustworthy.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
