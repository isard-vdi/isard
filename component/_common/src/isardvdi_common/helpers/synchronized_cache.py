#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Thread-safe cachetools caches.

cachetools caches are **not** thread-safe. Every read (``__getitem__``,
``__contains__``, ``__iter__``, ``__len__``, ``get``) and every write
(``__setitem__``, ``__delitem__``, ``pop``, ``popitem``, ``clear``) mutates an
internal time/order linked list — reads call ``expire()`` / move-to-MRU, writes
call ``popitem()`` (``key = next(iter(self.__links))``). Two OS threads racing
those mutations corrupt the structure, surfacing as
``RuntimeError: OrderedDict mutated during iteration`` (and sibling
``KeyError``/``TypeError`` from the same corruption).

``isardvdi_common`` is a shared library installed into containers that run under
real preemptive OS threads — apiv4's 128-worker ``asyncio.to_thread`` executor,
engine's ``ThreadPoolExecutor``, the notifier RQ worker — so its module-global
caches must be safe under true multithreading (and remain harmless under gevent
greenlets and single-thread asyncio). See tiquet #1096.

These classes serialise **every** entry point on one internal lock. Swapping a
cache definition from ``TTLCache(...)`` to ``SynchronizedTTLCache(...)`` makes
all of its existing call sites — the ``@cached`` decorator's get/set, manual
``cache[k] = v`` / ``del`` / ``.pop()`` / ``.clear()``, and the easy-to-miss
``expire()``-on-read paths — thread-safe without touching the call sites.

The lock is a reentrant ``RLock`` because cachetools dispatches between these
methods on the same thread (``Cache.__setitem__`` calls ``self.popitem()``;
``MutableMapping.clear``/``pop``/``setdefault`` call ``self[...]``), so a plain
``Lock`` would self-deadlock. The lock guards only the in-memory dict ops, never
an I/O call, so contention is negligible.

Note: this gives **structural** safety, not memoization atomicity. ``@cached``
still does check-then-set as two separate locked ops, so two simultaneous misses
may both run the wrapped function — benign for the idempotent reads these caches
hold. Pass ``@cached(cache, lock=cache.lock)`` if you also want the decorator's
check-then-set coordinated on the same lock.
"""

import threading

from cachetools import LRUCache, TTLCache


class _SynchronizedCacheMixin:
    """Mixin that wraps every cache entry point in a reentrant lock.

    Mix it in **before** a concrete cachetools cache so ``super()`` resolves to
    that cache, e.g. ``class C(_SynchronizedCacheMixin, TTLCache)``.
    """

    def __init__(self, *args, **kwargs):
        # Set the lock before delegating: the overridden methods reference it,
        # and a future cachetools version could touch them during __init__.
        self.lock = threading.RLock()
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        with self.lock:
            return super().__getitem__(key)

    def __setitem__(self, key, value):
        with self.lock:
            super().__setitem__(key, value)

    def __delitem__(self, key):
        with self.lock:
            super().__delitem__(key)

    def __contains__(self, key):
        with self.lock:
            return super().__contains__(key)

    def __iter__(self):
        # Snapshot the keys under the lock so callers can iterate after release
        # without risking a concurrent structural mutation mid-iteration.
        with self.lock:
            return iter(list(super().__iter__()))

    def __len__(self):
        with self.lock:
            return super().__len__()

    def get(self, *args, **kwargs):
        with self.lock:
            return super().get(*args, **kwargs)

    def pop(self, *args, **kwargs):
        with self.lock:
            return super().pop(*args, **kwargs)

    def setdefault(self, *args, **kwargs):
        with self.lock:
            return super().setdefault(*args, **kwargs)

    def popitem(self):
        with self.lock:
            return super().popitem()

    def clear(self):
        with self.lock:
            super().clear()


class SynchronizedTTLCache(_SynchronizedCacheMixin, TTLCache):
    """Thread-safe :class:`cachetools.TTLCache`. Drop-in replacement."""


class SynchronizedLRUCache(_SynchronizedCacheMixin, LRUCache):
    """Thread-safe :class:`cachetools.LRUCache`. Drop-in replacement."""
