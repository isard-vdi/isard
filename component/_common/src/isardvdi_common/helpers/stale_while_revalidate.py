#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Stale-while-revalidate caches for expensive, slowly-changing aggregates.

A plain ``TTLCache`` turns every expiry into a blocking miss, and
``cachetools``' ``@cached`` has no single-flight: every caller arriving while
the entry is recomputed recomputes it too. For an aggregate that scans
six-figure tables and is polled continuously by a dashboard that is the whole
cost — the cache only helps callers landing inside the same window, and when the
poll period is longer than the TTL the hit rate collapses to zero exactly where
it was needed.

These caches never make a warm caller wait: a stale entry is returned
immediately and exactly one background refresh is started. Only the very first
call blocks, and it blocks once for all concurrent callers. The last good value
keeps being served while the database is slow or unreachable, which for admin
aggregates beats propagating the error.

**Threading.** State is guarded by a real ``threading.Lock``: the consumers are
apiv4's ``asyncio.to_thread`` executor, engine's ``ThreadPoolExecutor`` and RQ
workers, i.e. preemptive OS threads. Refreshes run on ONE lazily started daemon
worker shared by every cache in the process, so a service that imports this
module but never goes stale pays no thread cost, and N stale caches can never
hold N connections out of the RethinkDB pool (``RETHINKDB_POOL_SIZE``) and
starve request traffic. The queue cannot grow past one job per cache — a cache
with a refresh in flight never queues another — so a slow refresh delays other
caches' refreshes (they keep serving their current value meanwhile) rather than
piling up work.

Usage::

    _cache = StaleWhileRevalidate(ttl=30)

    def get_data():
        return _cache.get(lambda: expensive_query())

``ttl=0`` disables caching (every call fetches) — the knob development wants.
"""

import functools
import logging
import threading
import time
from collections import OrderedDict
from queue import Queue
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# A failed background refresh keeps serving the stale value; retrying on the
# very next request would hammer a database that is already struggling, so the
# entry is only allowed to go stale again after this many seconds.
MIN_RETRY_INTERVAL_S = 2.0

_refresh_queue: "Queue[Callable[[], None]]" = Queue()
_refresh_worker: Optional[threading.Thread] = None
_refresh_worker_lock = threading.Lock()


def _refresh_loop() -> None:
    while True:
        job = _refresh_queue.get()
        try:
            job()
        except Exception:
            # Jobs handle their own errors; this only catches a bug in the job
            # wrapper itself, which must not kill the shared worker.
            log.exception("swr_refresh_worker_job_crashed")
        finally:
            # Keeps ``_refresh_queue.join()`` meaningful, which is how tests
            # wait for a background refresh without sleeping.
            _refresh_queue.task_done()


def _submit_refresh(job: Callable[[], None]) -> None:
    """Queue a refresh on the process-wide daemon worker, starting it lazily."""
    global _refresh_worker
    if _refresh_worker is None:
        with _refresh_worker_lock:
            if _refresh_worker is None:
                _refresh_worker = threading.Thread(
                    target=_refresh_loop, name="swr-refresh", daemon=True
                )
                _refresh_worker.start()
    _refresh_queue.put(job)


class _Entry:
    """One cached value plus the state machine that guards its refresh."""

    __slots__ = ("value", "has_value", "fetched_at", "refreshing", "ready", "error")

    def __init__(self) -> None:
        self.value: Any = None
        # Explicit flag rather than ``value is None`` so a fetch that legitimately
        # returns None is cached instead of re-running on every call.
        self.has_value = False
        self.fetched_at = 0.0
        self.refreshing = False
        self.ready = threading.Event()
        self.error: Optional[BaseException] = None


class _StaleWhileRevalidateBase:
    """Read path shared by the plain and keyed caches."""

    def __init__(self, ttl: float, name: Optional[str] = None) -> None:
        self.ttl = ttl
        self.name = name or type(self).__name__
        self._lock = threading.Lock()

    def _read(self, entry_of: Callable[[], _Entry], fetch: Callable[[], Any]) -> Any:
        while True:
            entry = entry_of()
            with self._lock:
                if entry.has_value:
                    stale = (time.monotonic() - entry.fetched_at) >= self.ttl
                    if stale and not entry.refreshing:
                        entry.refreshing = True
                        _submit_refresh(self._refresh_job(entry, fetch))
                    return entry.value
                if entry.refreshing:
                    ready = entry.ready
                    owner = False
                else:
                    entry.refreshing = True
                    entry.ready = ready = threading.Event()
                    entry.error = None
                    owner = True

            if not owner:
                ready.wait()
                with self._lock:
                    if entry.has_value:
                        return entry.value
                    error = entry.error
                if error is not None:
                    raise error
                # Invalidated mid-flight (clear()): start over on a fresh entry.
                continue

            try:
                value = fetch()
            except BaseException as exc:
                with self._lock:
                    entry.refreshing = False
                    entry.error = exc
                ready.set()
                raise
            with self._lock:
                entry.value = value
                entry.has_value = True
                entry.fetched_at = time.monotonic()
                entry.refreshing = False
                entry.error = None
            ready.set()
            return value

    def _refresh_job(
        self, entry: _Entry, fetch: Callable[[], Any]
    ) -> Callable[[], None]:
        def job() -> None:
            try:
                value = fetch()
            except Exception:
                log.warning(
                    "swr_background_refresh_failed name=%s", self.name, exc_info=True
                )
                with self._lock:
                    # Keep serving what we have, but hold off before retrying.
                    entry.fetched_at = (
                        time.monotonic() - self.ttl + MIN_RETRY_INTERVAL_S
                    )
                    entry.refreshing = False
                return
            with self._lock:
                entry.value = value
                entry.has_value = True
                entry.fetched_at = time.monotonic()
                entry.refreshing = False

        return job


class StaleWhileRevalidate(_StaleWhileRevalidateBase):
    """Cache one value, refreshed in the background once it goes stale."""

    def __init__(self, ttl: float, name: Optional[str] = None) -> None:
        super().__init__(ttl, name)
        self._entry = _Entry()

    @property
    def currsize(self) -> int:
        """Populated entries — 0 or 1. Mirrors the ``cachetools`` attribute."""
        with self._lock:
            return 1 if self._entry.has_value else 0

    def clear(self) -> None:
        """Drop the cached value; the next ``get`` is a cold start.

        Replaces the entry outright, so a refresh already in flight writes into
        the orphaned entry and cannot resurrect invalidated data.
        """
        with self._lock:
            self._entry = _Entry()

    def get(self, fetch: Callable[[], Any]) -> Any:
        if self.ttl <= 0:
            return fetch()
        return self._read(self._current_entry, fetch)

    def _current_entry(self) -> _Entry:
        with self._lock:
            return self._entry


class KeyedStaleWhileRevalidate(_StaleWhileRevalidateBase):
    """Keyed variant: one independently refreshed entry per key, LRU-bounded."""

    def __init__(
        self, ttl: float, maxsize: int = 10, name: Optional[str] = None
    ) -> None:
        super().__init__(ttl, name)
        self.maxsize = maxsize
        self._entries: "OrderedDict[Any, _Entry]" = OrderedDict()

    @property
    def currsize(self) -> int:
        with self._lock:
            return sum(1 for entry in self._entries.values() if entry.has_value)

    def clear(self) -> None:
        """Drop every cached value; see :meth:`StaleWhileRevalidate.clear`."""
        with self._lock:
            self._entries = OrderedDict()

    def get(self, key: Any, fetch: Callable[[], Any]) -> Any:
        if self.ttl <= 0:
            return fetch()
        return self._read(lambda: self._entry_for(key), fetch)

    def _entry_for(self, key: Any) -> _Entry:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self.maxsize:
                    self._evict_one()
                entry = _Entry()
                self._entries[key] = entry
            else:
                self._entries.move_to_end(key)
            return entry

    def _evict_one(self) -> None:
        """Drop one entry: an empty one first, else the least recently used.

        Preferring empty entries keeps a burst of keys whose fetch always fails
        (an unrecognised argument, say) from evicting the populated entries that
        are doing the actual work.
        """
        for key, entry in self._entries.items():
            if not entry.refreshing and not entry.has_value:
                del self._entries[key]
                return
        for key, entry in self._entries.items():
            if not entry.refreshing:
                del self._entries[key]
                return
        # Every entry is mid-refresh: let the dict grow rather than evict one
        # whose waiters are blocked on it.


def swr_cached(cache: StaleWhileRevalidate) -> Callable:
    """Read a zero-argument function through a :class:`StaleWhileRevalidate`.

    Drop-in shape replacement for ``cachetools``' ``@cached``, so an existing
    call site only swaps the decorator::

        @classmethod
        @swr_cached(_users_stats_cache)
        def get_users_stats(cls) -> dict: ...
    """

    def decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return cache.get(lambda: func(*args, **kwargs))

        return wrapper

    return decorate


def swr_cached_keyed(
    cache: KeyedStaleWhileRevalidate, key: Callable[..., Any]
) -> Callable:
    """Keyed variant; ``key`` maps the call's arguments to a cache key."""

    def decorate(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return cache.get(key(*args, **kwargs), lambda: func(*args, **kwargs))

        return wrapper

    return decorate
