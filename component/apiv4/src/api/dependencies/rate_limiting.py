"""
Sliding-window rate limiters, per-process (not shared across uvicorn workers).

The direct viewer endpoints limit silently: the caller returns a generic 404
instead of 429, making rate limiting invisible to the attacker. Token entropy
(256 bits) makes brute-force infeasible; this is defense-in-depth.

The register endpoints answer 429 with a ``Retry-After`` date.
"""

import os
import time
from collections import defaultdict
from email.utils import formatdate
from threading import Lock
from typing import Awaitable, Callable, Hashable

from api.dependencies.jwt_token import TokenPayload, get_remote_addr
from api.services.error import Error
from fastapi import Depends, Request


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
        return self.hit(ip) > 0

    def hit(self, key: Hashable) -> float:
        """Records a request for key. Returns the seconds until key is allowed
        again, or 0 if this request is allowed."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            requests = [t for t in self._requests[key] if t > cutoff]
            requests.append(now)
            self._requests[key] = requests
            if len(requests) > self.max_requests:
                return requests[-self.max_requests] + self.window_seconds - now
            return 0.0


# Singleton for the direct viewer endpoints
direct_viewer_limiter = RateLimiter()

register_user_limiter = RateLimiter(max_requests=10, window_seconds=1 * 60)
register_ip_limiter = RateLimiter(max_requests=300, window_seconds=5 * 60)


def register_rate_limit(
    token_dependency: Callable[..., Awaitable[TokenPayload]],
) -> Callable[..., Awaitable[None]]:
    async def dependency(
        request: Request, payload: TokenPayload = Depends(token_dependency)
    ) -> None:
        # The user is checked first so a token over its own limit can't exhaust the budget of an IP
        retry_after = register_user_limiter.hit(
            (payload["provider"], payload["category_id"], payload["user_id"])
        ) or register_ip_limiter.hit(get_remote_addr(request))
        if retry_after:
            error = Error("too_many_requests", "Too many registration attempts.")
            error.headers = {
                "Retry-After": formatdate(time.time() + retry_after, usegmt=True)
            }
            raise error

    return dependency


# Timing normalization constants
MIN_RESPONSE_TIME = float(os.environ.get("DIRECT_VIEWER_MIN_RESPONSE_TIME", "3.0"))

ALLOWED_PROTOCOLS = {
    "browser-vnc",
    "browser-rdp",
    "file-spice",
    "file-rdpgw",
}
