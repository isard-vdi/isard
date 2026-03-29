#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Stale-While-Revalidate Cache Pattern for gevent applications.

This module provides cache classes that return stale data immediately while
refreshing in the background, preventing request queueing under load.

Classes:
    StaleWhileRevalidate: For functions without parameters
    KeyedStaleWhileRevalidate: For functions with parameters (uses key function)
"""

import logging
import time

import gevent
from gevent.event import Event

log = logging.getLogger(__name__)

MIN_RETRY_INTERVAL = 2


class StaleWhileRevalidate:
    """
    Cache that returns immediately with stale data while refreshing in background.

    Behavior:
    - Cold start: blocks until first data is available
    - Warm + fresh: returns cached data immediately
    - Warm + stale: returns stale data immediately, triggers background refresh

    This prevents request queueing when queries take longer than TTL.

    Usage:
        _cache = StaleWhileRevalidate(ttl=60)

        def get_data():
            def fetch():
                return expensive_query()
            return _cache.get(fetch)
    """

    def __init__(self, ttl):
        """
        Initialize cache with TTL in seconds.

        Args:
            ttl: Time-to-live in seconds before data is considered stale
        """
        self.ttl = ttl
        self._cache = None
        self._cache_time = 0
        self._refreshing = False
        self._ready = Event()

    def _refresh_sync(self, fetch_func):
        """Synchronous refresh for cold start."""
        try:
            self._cache = fetch_func()
            self._cache_time = time.time()
        finally:
            self._refreshing = False

    def _refresh(self, fetch_func):
        """Background refresh for stale cache."""
        try:
            self._cache = fetch_func()
            self._cache_time = time.time()
        except Exception:
            log.warning("Background cache refresh failed, will retry after backoff")
            self._cache_time = time.time() - self.ttl + MIN_RETRY_INTERVAL
        finally:
            self._refreshing = False

    def get(self, fetch_func):
        """
        Get cached data, refreshing in background if stale.

        Args:
            fetch_func: Callable that returns fresh data

        Returns:
            Cached data (may be stale if refresh is in progress)
        """
        # Cold start - must wait for data
        if self._cache is None:
            if not self._refreshing:
                self._refreshing = True
                self._ready.clear()
                try:
                    self._refresh_sync(fetch_func)
                finally:
                    self._ready.set()
            else:
                # Another greenlet is fetching, wait for it
                self._ready.wait()
            return self._cache

        # Warm cache - return immediately, background refresh if stale
        now = time.time()
        if (now - self._cache_time) >= self.ttl and not self._refreshing:
            self._refreshing = True
            gevent.spawn(self._refresh, fetch_func)

        return self._cache


class KeyedStaleWhileRevalidate:
    """
    Keyed version of StaleWhileRevalidate for functions with parameters.

    Each unique key gets its own cache entry with independent TTL tracking.
    Includes LRU-like eviction when maxsize is exceeded.

    Usage:
        _cache = KeyedStaleWhileRevalidate(ttl=60, maxsize=10)

        def get_data(kind):
            def fetch():
                return expensive_query(kind)
            return _cache.get(kind, fetch)
    """

    def __init__(self, ttl, maxsize=10):
        """
        Initialize cache with TTL and max entries.

        Args:
            ttl: Time-to-live in seconds before data is considered stale
            maxsize: Maximum number of cache entries (evicts oldest when exceeded)
        """
        self.ttl = ttl
        self.maxsize = maxsize
        self._caches = {}  # key -> {cache, cache_time, refreshing, ready}

    def _get_entry(self, key):
        """Get or create cache entry for key, with LRU eviction."""
        if key not in self._caches:
            if len(self._caches) >= self.maxsize:
                # Evict oldest entry, skipping entries currently being refreshed
                evictable = {
                    k: v for k, v in self._caches.items() if not v["refreshing"]
                }
                if evictable:
                    oldest_key = min(
                        evictable, key=lambda k: evictable[k]["cache_time"]
                    )
                    del self._caches[oldest_key]
            self._caches[key] = {
                "cache": None,
                "cache_time": 0,
                "refreshing": False,
                "ready": Event(),
            }
        return self._caches[key]

    def _refresh_sync(self, entry, fetch_func):
        """Synchronous refresh for cold start."""
        try:
            entry["cache"] = fetch_func()
            entry["cache_time"] = time.time()
        finally:
            entry["refreshing"] = False

    def _refresh(self, entry, fetch_func):
        """Background refresh for stale cache."""
        try:
            entry["cache"] = fetch_func()
            entry["cache_time"] = time.time()
        except Exception:
            log.warning(
                "Background keyed cache refresh failed, will retry after backoff"
            )
            entry["cache_time"] = time.time() - self.ttl + MIN_RETRY_INTERVAL
        finally:
            entry["refreshing"] = False

    def get(self, key, fetch_func):
        """
        Get cached data for key, refreshing in background if stale.

        Args:
            key: Cache key (hashable)
            fetch_func: Callable that returns fresh data

        Returns:
            Cached data (may be stale if refresh is in progress)
        """
        entry = self._get_entry(key)

        # Cold start for this key - must wait for data
        if entry["cache"] is None:
            if not entry["refreshing"]:
                entry["refreshing"] = True
                entry["ready"].clear()
                try:
                    self._refresh_sync(entry, fetch_func)
                finally:
                    entry["ready"].set()
            else:
                # Another greenlet is fetching this key, wait for it
                entry["ready"].wait()
            return entry["cache"]

        # Warm cache - return immediately, background refresh if stale
        now = time.time()
        if (now - entry["cache_time"]) >= self.ttl and not entry["refreshing"]:
            entry["refreshing"] = True
            gevent.spawn(self._refresh, entry, fetch_func)

        return entry["cache"]
