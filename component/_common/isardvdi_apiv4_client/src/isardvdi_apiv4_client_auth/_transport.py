"""A process-wide httpx transport, so API clients reuse connections.

``build_client()`` has to return a fresh client on every call — the
service JWT it mints only lives 20s — and each ``httpx.Client`` builds
its own connection pool. Sharing the transport, which is what actually
owns the pool, is what stops every API call paying for a handshake.

Two details make it safe. Call sites use ``with build_client(...)``, and
``httpx.Client.close()`` closes its transport, so ``SharedTransport``
swallows ``close()``. And a child process starts from an empty cache,
because sockets opened before a ``fork()`` still belong to the parent.

Mirrors the module-scoped pool in
``isardvdi_common.connections.rethink_shared_connection``: lazily built
behind a double-checked lock, bounded by an env-tunable acquire timeout,
and reset through an explicit test-only seam. The at-fork reset follows
``isardvdi_common.helpers.stale_while_revalidate``.
"""

import os
import threading
from os import environ, getpid
from typing import Any, Dict, Tuple

import httpx

# Bound on how long a request may block waiting for a free connection.
# Sharing the transport turned the pool's connections into a budget every
# caller draws from, and httpx waits for one forever by default, so an
# exhausted pool would wedge the caller instead of failing. Tuning it
# means declaring ``API_CLIENT_POOL_TIMEOUT_SEC`` in the service's compose
# environment as well, the way the rethink pool knobs are.
_POOL_TIMEOUT_S = float(environ.get("API_CLIENT_POOL_TIMEOUT_SEC", "10"))

# Only the pool component is set: waiting for a shared connection is the
# one delay this module introduces, so the rest keeps httpx's behaviour.
POOL_TIMEOUT = httpx.Timeout(None, pool=_POOL_TIMEOUT_S)

# httpx's own defaults, except for the expiry: it drops an idle connection
# after 5s, which is shorter than every loop that calls the API, so sharing
# the pool would still leave each call paying for a handshake. It has to
# stay under apiv4's ``--timeout-keep-alive`` (120s, in
# component/apiv4/docker/Dockerfile) -- whichever side holds on longer ends
# up sending on a connection the other has already closed.
POOL_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=90.0,
)


class SharedTransport(httpx.BaseTransport):
    """An ``httpx`` transport whose connection pool outlives its clients."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.inner.handle_request(request)

    def close(self) -> None:
        """Deliberately a no-op: the pool belongs to this module."""


_transports: Dict[Tuple[int, Any], SharedTransport] = {}
_transports_lock = threading.Lock()


def shared_transport(*, verify: Any) -> SharedTransport:
    """Return the transport this process talks to ``verify`` peers with.

    httpx ignores a client's ``verify`` once given an explicit transport,
    so it has to key the cache instead. Lazily created, so importing this
    module opens no sockets.
    """
    key = (getpid(), verify)

    transport = _transports.get(key)
    if transport is not None:
        return transport

    with _transports_lock:
        transport = _transports.get(key)
        if transport is None:
            transport = SharedTransport(
                httpx.HTTPTransport(verify=verify, limits=POOL_LIMITS)
            )
            _transports[key] = transport

    return transport


def _reset_after_fork() -> None:
    """Start the child from scratch. The inherited transports hold the
    parent's sockets, and ``_transports_lock`` may have been held by
    another thread at the instant of the fork, which would deadlock the
    first caller in the child."""
    global _transports_lock

    _transports_lock = threading.Lock()
    _transports.clear()


if hasattr(os, "register_at_fork"):  # not available on every platform
    os.register_at_fork(after_in_child=_reset_after_fork)


def _clear_transports_for_tests() -> None:
    """Test-only seam. Production code MUST NOT call this — the pools are
    meant to live as long as the process. It lets unit tests start from an
    empty cache without reaching into this module's private state."""
    with _transports_lock:
        _transports.clear()
