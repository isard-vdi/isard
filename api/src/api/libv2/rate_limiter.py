import os
import time
from collections import defaultdict
from threading import Lock

from ..views.decorators import get_remote_addr


class RateLimiter:
    """Silent sliding-window rate limiter.

    When limit is exceeded, is_limited() returns True. The caller
    returns the same generic 404 as any other failure — making rate
    limiting invisible to the attacker.

    Per-process (not shared across gunicorn workers). Intentional:
    token entropy (256 bits) makes brute-force infeasible; this is
    defense-in-depth, not a precision boundary.
    """

    def __init__(self, max_requests=None, window_seconds=None):
        self.max_requests = max_requests or int(
            os.environ.get("DIRECT_VIEWER_RATE_LIMIT", "30")
        )
        self.window_seconds = window_seconds or int(
            os.environ.get("DIRECT_VIEWER_RATE_WINDOW", "60")
        )
        self._requests = defaultdict(list)
        self._lock = Lock()

    def is_limited(self, request) -> bool:
        """Returns True if IP exceeds rate limit. Never raises."""
        ip = get_remote_addr(request)
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]
            if len(self._requests[ip]) >= self.max_requests:
                self._requests[ip].append(now)
                return True
            self._requests[ip].append(now)
            return False
