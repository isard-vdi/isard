"""
Silent sliding-window rate limiter for direct viewer token endpoints.

When limit is exceeded, returns True. The caller returns a generic 404
instead of 429 — making rate limiting invisible to the attacker.

Per-process (not shared across uvicorn workers). Token entropy (256 bits)
makes brute-force infeasible; this is defense-in-depth.
"""

import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request


class RateLimiter:
    def __init__(self, max_requests=None, window_seconds=None):
        self.max_requests = max_requests or int(
            os.environ.get("DIRECT_VIEWER_RATE_LIMIT", "30")
        )
        self.window_seconds = window_seconds or int(
            os.environ.get("DIRECT_VIEWER_RATE_WINDOW", "60")
        )
        self._requests = defaultdict(list)
        self._lock = Lock()

    def is_limited(self, request: Request) -> bool:
        """Returns True if IP exceeds rate limit. Never raises."""
        ip = request.headers.get(
            "x-forwarded-for", request.client.host if request.client else "unknown"
        )
        if "," in ip:
            ip = ip.split(",")[0].strip()
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]
            if len(self._requests[ip]) >= self.max_requests:
                self._requests[ip].append(now)
                return True
            self._requests[ip].append(now)
            return False


# Singleton for the direct viewer endpoints
direct_viewer_limiter = RateLimiter()

# Timing normalization constants
MIN_RESPONSE_TIME = float(os.environ.get("DIRECT_VIEWER_MIN_RESPONSE_TIME", "3.0"))

ALLOWED_PROTOCOLS = {
    "browser-vnc",
    "browser-rdp",
    "file-spice",
    "file-rdpgw",
}
