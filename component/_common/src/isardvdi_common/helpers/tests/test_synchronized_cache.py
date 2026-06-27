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


class _CountingLock:
    """RLock wrapper that counts acquisitions, to prove an entry point is
    actually serialised on the cache's own lock."""

    def __init__(self, inner):
        self._inner = inner
        self.acquisitions = 0

    def __enter__(self):
        self.acquisitions += 1
        return self._inner.__enter__()

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def acquire(self, *args, **kwargs):
        self.acquisitions += 1
        return self._inner.acquire(*args, **kwargs)

    def release(self):
        return self._inner.release()


def test_currsize_repr_and_expire_are_synchronized():
    """``currsize``, ``__repr__`` and the public ``expire()`` are NOT pure reads
    on a TTLCache: ``_TimedCache.currsize``/``__repr__`` call ``self.expire()``,
    which structurally unlinks expired entries. If they bypass the lock they can
    corrupt a concurrently-locked writer (regression of #1096 via a side door).
    Every such entry point must acquire the cache's own lock."""
    cache = SynchronizedTTLCache(maxsize=5, ttl=60)
    cache["a"] = 1
    cache.lock = _CountingLock(cache.lock)

    before = cache.lock.acquisitions
    _ = cache.currsize
    assert cache.lock.acquisitions > before, "currsize did not go through the lock"

    before = cache.lock.acquisitions
    repr(cache)
    assert cache.lock.acquisitions > before, "__repr__ did not go through the lock"

    before = cache.lock.acquisitions
    cache.expire()
    assert cache.lock.acquisitions > before, "expire() did not go through the lock"


def test_iter_returns_a_snapshot_safe_against_later_mutation():
    """``__iter__`` must materialise the keys under the lock and hand back a
    snapshot, so a caller can iterate after the cache is mutated — the
    ``api_admin.clear_admin_table_list_cache`` ``list(cache)`` + ``pop`` pattern.
    A lazy ``super().__iter__()`` (``Cache.__iter__`` is ``iter(self.__data)``)
    would raise ``RuntimeError: dictionary changed size during iteration``."""
    cache = SynchronizedLRUCache(maxsize=500)
    for i in range(100):
        cache[i] = i
    iterator = iter(cache)  # snapshot taken here, under the lock
    for i in range(100, 200):  # mutate AFTER obtaining the iterator
        cache[i] = i
    drained = list(iterator)  # consuming the snapshot must not raise
    assert len(drained) == 100  # froze the 100 keys live at iter() time


def test_iterate_then_pop_under_concurrent_writes():
    """The exact ``api_admin`` invalidation shape: a thread repeatedly does
    ``for k in list(cache): cache.pop(k, None)`` while others hammer writes and
    evictions. No structural-corruption exception may escape. Work is bounded so
    the test stays fast under RLock contention."""
    cache = SynchronizedLRUCache(maxsize=64)
    errors = []

    def writer(wid):
        try:
            for i in range(4000):
                cache[hashkey(wid, i % 200)] = i
        except Exception as exc:
            errors.append(f"writer {type(exc).__name__}: {exc}")

    def invalidator():
        try:
            for _ in range(300):
                for k in list(cache):  # snapshot iterate
                    cache.pop(k, None)  # tolerant delete
        except Exception as exc:
            errors.append(f"invalidator {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=writer, args=(w,)) for w in range(4)]
    threads.append(threading.Thread(target=invalidator))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"iterate+pop corruption: {errors[:5]}"
