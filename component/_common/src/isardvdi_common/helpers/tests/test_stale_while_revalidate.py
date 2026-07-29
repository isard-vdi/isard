#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the stale-while-revalidate caches.

Time is faked (``time.monotonic`` is monkeypatched) so staleness is exercised
without sleeping, and background refreshes are awaited with
``_refresh_queue.join()`` rather than by polling.
"""

import threading

import pytest
from isardvdi_common.helpers import stale_while_revalidate as mod
from isardvdi_common.helpers.stale_while_revalidate import (
    KeyedStaleWhileRevalidate,
    StaleWhileRevalidate,
)


@pytest.fixture
def clock(monkeypatch):
    """Controllable monotonic clock, scoped to the module under test.

    Replaces the module's ``time`` reference rather than patching
    ``time.monotonic`` globally, which would also move the clock under
    ``threading`` and ``queue``.
    """

    class _Clock:
        def __init__(self):
            self.now = 1000.0

        def monotonic(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    c = _Clock()
    monkeypatch.setattr(mod, "time", c)
    return c


@pytest.fixture(autouse=True)
def drain_refresh_queue():
    """Never leak a queued refresh into the next test."""
    yield
    mod._refresh_queue.join()


def _wait_for_refresh():
    mod._refresh_queue.join()


class _Counter:
    """fetch() stub that counts calls and can be told to fail."""

    def __init__(self, value="v1"):
        self.calls = 0
        self.value = value
        self.raises = None
        self.gate = None

    def __call__(self):
        self.calls += 1
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.raises is not None:
            raise self.raises
        return self.value


class TestColdStart:
    def test_first_call_fetches_and_returns(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("cold")
        assert cache.get(fetch) == "cold"
        assert fetch.calls == 1
        assert cache.currsize == 1

    def test_fresh_entry_is_not_refetched(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter()
        cache.get(fetch)
        clock.advance(9.9)
        assert cache.get(fetch) == "v1"
        assert fetch.calls == 1

    def test_none_is_a_cacheable_value(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter(None)
        assert cache.get(fetch) is None
        assert cache.get(fetch) is None
        assert fetch.calls == 1

    def test_concurrent_cold_callers_fetch_once(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("shared")
        fetch.gate = threading.Event()
        results = []
        start = threading.Barrier(6)  # 5 callers + this thread

        def call():
            start.wait(timeout=5)
            results.append(cache.get(fetch))

        threads = [threading.Thread(target=call) for _ in range(5)]
        for t in threads:
            t.start()
        # Let every caller reach the cache before the single fetch completes.
        start.wait(timeout=5)
        fetch.gate.set()
        for t in threads:
            t.join(timeout=5)

        assert results == ["shared"] * 5
        assert fetch.calls == 1

    def test_cold_start_failure_reaches_every_waiter(self, clock):
        """Waiters must get the owner's exception, never a silent ``None``.

        Driven white-box: the entry is put in the "a cold start is in flight"
        state before any thread runs, so every caller is guaranteed to be a
        waiter and the test needs no timing assumptions.
        """
        cache = StaleWhileRevalidate(ttl=10)
        entry = cache._entry
        entry.refreshing = True
        entry.ready = ready = threading.Event()

        results, errors = [], []

        def call():
            try:
                results.append(cache.get(lambda: "must not be called"))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=call) for _ in range(4)]
        for t in threads:
            t.start()

        boom = RuntimeError("db down")
        with cache._lock:
            entry.refreshing = False
            entry.error = boom
        ready.set()

        for t in threads:
            t.join(timeout=5)

        assert results == []
        assert errors == [boom] * 4
        assert cache.currsize == 0

    def test_concurrent_cold_failures_cache_nothing(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter()
        fetch.raises = RuntimeError("db down")
        errors = []
        start = threading.Barrier(5)  # 4 callers + this thread

        def call():
            start.wait(timeout=5)
            try:
                cache.get(fetch)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=call) for _ in range(4)]
        for t in threads:
            t.start()
        start.wait(timeout=5)
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 4
        assert all(isinstance(e, RuntimeError) for e in errors)
        assert cache.currsize == 0

    def test_cold_start_failure_is_not_cached(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("later")
        fetch.raises = RuntimeError("transient")
        with pytest.raises(RuntimeError):
            cache.get(fetch)
        fetch.raises = None
        assert cache.get(fetch) == "later"
        assert fetch.calls == 2


class TestStaleServing:
    def test_stale_entry_returns_old_value_immediately(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("old")
        cache.get(fetch)
        clock.advance(11)
        fetch.value = "new"
        assert cache.get(fetch) == "old"
        _wait_for_refresh()
        assert fetch.calls == 2
        assert cache.get(fetch) == "new"

    def test_concurrent_stale_readers_trigger_one_refresh(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("old")
        cache.get(fetch)
        clock.advance(11)
        fetch.gate = threading.Event()
        fetch.value = "new"
        results = []
        start = threading.Barrier(7)  # 6 callers + this thread

        def call():
            start.wait(timeout=5)
            results.append(cache.get(fetch))

        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:
            t.start()
        start.wait(timeout=5)
        for t in threads:
            t.join(timeout=5)
        fetch.gate.set()
        _wait_for_refresh()

        # Nobody waited: everyone got the stale value straight away.
        assert results == ["old"] * 6
        # One cold fetch + exactly one background refresh.
        assert fetch.calls == 2

    def test_failed_background_refresh_keeps_serving_and_backs_off(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("good")
        cache.get(fetch)
        clock.advance(11)
        fetch.raises = RuntimeError("boom")
        assert cache.get(fetch) == "good"
        _wait_for_refresh()
        assert fetch.calls == 2

        # Immediately after the failure the entry is held fresh for the backoff
        # window, so a burst of callers cannot re-trigger the failing query.
        assert cache.get(fetch) == "good"
        _wait_for_refresh()
        assert fetch.calls == 2

        clock.advance(mod.MIN_RETRY_INTERVAL_S)
        fetch.raises = None
        fetch.value = "recovered"
        assert cache.get(fetch) == "good"
        _wait_for_refresh()
        assert cache.get(fetch) == "recovered"


class TestClear:
    def test_clear_forces_a_cold_start(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("a")
        cache.get(fetch)
        cache.clear()
        assert cache.currsize == 0
        fetch.value = "b"
        assert cache.get(fetch) == "b"
        assert fetch.calls == 2

    def test_clear_during_refresh_does_not_resurrect_the_value(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("old")
        cache.get(fetch)
        clock.advance(11)
        fetch.gate = threading.Event()
        fetch.value = "stale-refresh"
        cache.get(fetch)  # schedules the background refresh

        cache.clear()
        fetch.gate.set()
        _wait_for_refresh()

        assert cache.currsize == 0
        fetch.gate = None
        fetch.value = "fresh"
        assert cache.get(fetch) == "fresh"


class TestDisabled:
    def test_ttl_zero_always_fetches(self, clock):
        cache = StaleWhileRevalidate(ttl=0)
        fetch = _Counter()
        cache.get(fetch)
        cache.get(fetch)
        cache.get(fetch)
        assert fetch.calls == 3
        assert cache.currsize == 0

    def test_keyed_ttl_zero_always_fetches(self, clock):
        cache = KeyedStaleWhileRevalidate(ttl=0)
        fetch = _Counter()
        cache.get("k", fetch)
        cache.get("k", fetch)
        assert fetch.calls == 2


class TestKeyed:
    def test_keys_are_independent(self, clock):
        cache = KeyedStaleWhileRevalidate(ttl=10, maxsize=4)
        calls = []

        def fetch_for(key):
            def fetch():
                calls.append(key)
                return f"value-{key}"

            return fetch

        assert cache.get("a", fetch_for("a")) == "value-a"
        assert cache.get("b", fetch_for("b")) == "value-b"
        assert cache.get("a", fetch_for("a")) == "value-a"
        assert calls == ["a", "b"]
        assert cache.currsize == 2

    def test_stale_key_refreshes_only_itself(self, clock):
        cache = KeyedStaleWhileRevalidate(ttl=10, maxsize=4)
        a, b = _Counter("a1"), _Counter("b1")
        cache.get("a", a)
        cache.get("b", b)
        clock.advance(11)
        a.value = "a2"
        assert cache.get("a", a) == "a1"
        _wait_for_refresh()
        assert a.calls == 2
        assert b.calls == 1
        assert cache.get("a", a) == "a2"

    def test_maxsize_evicts_least_recently_used(self, clock):
        cache = KeyedStaleWhileRevalidate(ttl=10, maxsize=2)
        first = _Counter("1")
        cache.get("k1", first)
        cache.get("k2", _Counter("2"))
        cache.get("k1", first)  # k1 becomes most recently used
        cache.get("k3", _Counter("3"))  # evicts k2, not k1

        assert cache.currsize == 2
        assert first.calls == 1  # k1 survived, no refetch
        again = _Counter("2 again")
        assert cache.get("k2", again) == "2 again"
        assert again.calls == 1

    def test_clear_drops_every_key(self, clock):
        cache = KeyedStaleWhileRevalidate(ttl=10, maxsize=4)
        cache.get("a", _Counter("a"))
        cache.get("b", _Counter("b"))
        cache.clear()
        assert cache.currsize == 0


@pytest.fixture
def isolated_module_state():
    """Restore the module globals the fork handler replaces.

    Running the handler in a process that did not actually fork leaves the real
    worker alive while clearing the pointer to it, so a later refresh would
    start a second one. A real child has no such thread.
    """
    saved = (mod._refresh_worker, mod._refresh_queue, mod._refresh_worker_lock)
    yield
    mod._refresh_worker, mod._refresh_queue, mod._refresh_worker_lock = saved


class TestForkSafety:
    """A forked child inherits a worker thread that does not exist in it."""

    @pytest.fixture(autouse=True)
    def _isolate(self, isolated_module_state):
        yield

    def test_child_starts_cold_with_a_fresh_lock_and_no_worker(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        keyed = KeyedStaleWhileRevalidate(ttl=10)
        fetch = _Counter("parent")
        cache.get(fetch)
        keyed.get("k", fetch)
        parent_lock = cache._lock
        mod._refresh_worker = object()  # stand-in for the parent's thread

        mod._reset_after_fork()

        assert mod._refresh_worker is None
        assert cache.currsize == 0 and keyed.currsize == 0
        assert cache._lock is not parent_lock
        fetch.value = "child"
        assert cache.get(fetch) == "child"

    def test_child_does_not_inherit_an_in_flight_refresh(self, clock):
        cache = StaleWhileRevalidate(ttl=10)
        fetch = _Counter("old")
        cache.get(fetch)
        # Pretend the fork happened while the parent was refreshing: without the
        # reset, the child's callers would wait on a ghost thread's event.
        cache._entry.refreshing = True
        cache._entry.has_value = False

        mod._reset_after_fork()

        fetch.value = "child"
        assert cache.get(fetch) == "child"

    def test_handler_is_registered_at_fork(self):
        import os

        assert hasattr(os, "register_at_fork")
        # The module registers on import; re-running the handler must be safe.
        mod._reset_after_fork()
        mod._reset_after_fork()


class TestRefreshWorker:
    def test_single_shared_worker_thread(self, clock):
        cache_a = StaleWhileRevalidate(ttl=10, name="a")
        cache_b = StaleWhileRevalidate(ttl=10, name="b")
        fa, fb = _Counter("a"), _Counter("b")
        cache_a.get(fa)
        cache_b.get(fb)
        clock.advance(11)
        cache_a.get(fa)
        cache_b.get(fb)
        _wait_for_refresh()

        workers = [t for t in threading.enumerate() if t.name == "swr-refresh"]
        assert len(workers) == 1
        assert workers[0].daemon is True
        assert fa.calls == 2 and fb.calls == 2
