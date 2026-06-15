"""Thread-safety tests for ``synchronized_cache``.

Regression coverage for tiquet #1096: cachetools caches are not thread-safe.
Under concurrent OS threads (apiv4's 128-worker executor, engine threads), a
plain ``TTLCache``/``LRUCache`` corrupts its internal linked list during
``popitem``/``expire``, surfacing as ``RuntimeError: OrderedDict mutated during
iteration`` (and sibling ``KeyError``/``TypeError`` from the same corruption).
The synchronized variants must serialise every entry point so none of that
escapes.
"""

import threading

import pytest
from cachetools.keys import hashkey
from isardvdi_common.helpers.synchronized_cache import (
    SynchronizedLRUCache,
    SynchronizedTTLCache,
)


def test_basic_ttl_mapping_semantics():
    """The synchronized cache behaves like the cachetools cache it wraps."""
    cache = SynchronizedTTLCache(maxsize=3, ttl=60)
    cache["a"] = 1
    cache["b"] = 2
    assert cache["a"] == 1
    assert "b" in cache
    assert len(cache) == 2
    assert cache.get("missing") is None
    assert cache.pop("a") == 1
    assert "a" not in cache
    assert set(cache) == {"b"}
    cache.clear()
    assert len(cache) == 0


def test_setitem_eviction_does_not_deadlock():
    """Filling past ``maxsize`` evicts via ``self.popitem()`` from inside
    ``__setitem__``. Both are guarded by the cache's own lock, so the lock MUST
    be reentrant (RLock); a plain Lock would self-deadlock here. Run in a worker
    thread and require it to finish, so a deadlocked implementation fails the
    test (timeout) instead of hanging the suite forever."""
    cache = SynchronizedTTLCache(maxsize=5, ttl=60)
    done = threading.Event()

    def fill():
        for i in range(50):  # 10x maxsize -> many evictions
            cache[i] = i
        done.set()

    t = threading.Thread(target=fill, daemon=True)
    t.start()
    t.join(timeout=10)
    assert done.is_set(), "setitem->popitem deadlocked (lock is not reentrant)"
    assert len(cache) == 5


def _hammer(cache, threads=16, iters=3000, keyspace=50):
    """Pound the cache from many threads with a key space larger than maxsize,
    forcing constant eviction (popitem) while other threads read (expire).
    Mirrors RethinkBase ``_update_cache`` writes racing ``@cached __getattr__``
    reads. Returns the list of UNEXPECTED exceptions (a missed read after a
    concurrent eviction is a legitimate KeyError and is not counted)."""
    errors = []

    def worker(wid):
        try:
            for i in range(iters):
                key = hashkey(wid, i % keyspace)
                cache[key] = i
                try:
                    _ = cache[key]
                except KeyError:
                    pass  # legitimately evicted by another thread — expected
        except Exception as exc:  # any escape here means structural corruption
            errors.append(f"{type(exc).__name__}: {exc}")

    workers = [threading.Thread(target=worker, args=(w,)) for w in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return errors


def test_synchronized_ttlcache_is_thread_safe_under_eviction():
    cache = SynchronizedTTLCache(maxsize=10, ttl=60)
    errors = _hammer(cache)
    assert errors == [], f"thread-safety violated: {errors[:5]}"


def test_synchronized_lrucache_is_thread_safe_under_eviction():
    cache = SynchronizedLRUCache(maxsize=10)
    errors = _hammer(cache)
    assert errors == [], f"thread-safety violated: {errors[:5]}"


def test_lock_attribute_is_reentrant():
    """The public ``lock`` is exposed (so ``@cached(cache, lock=cache.lock)``
    callers can share it) and is reentrant."""
    cache = SynchronizedTTLCache(maxsize=2, ttl=60)
    assert cache.lock.acquire()
    try:
        assert cache.lock.acquire(blocking=False)  # reentrant: same thread
        cache.lock.release()
    finally:
        cache.lock.release()
