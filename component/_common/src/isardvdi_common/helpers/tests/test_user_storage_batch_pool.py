"""Tests for ``_run_batches_in_pool``, ``_spawn_daemon``, and
``_spawn_daemon_later`` — replace the gevent-based fan-out and
fire-and-forget patterns in ``isardvdi_common.helpers.user_storage``.

See APIV4_THREADING_INCIDENT_ANALYSIS.md §3 Tier-C / §5.7 Pattern C.
"""

import threading
import time

import pytest
from isardvdi_common.helpers.user_storage import (
    _run_batches_in_pool,
    _spawn_daemon,
    _spawn_daemon_later,
)


def test_runs_each_batch_once_with_args_and_kwargs():
    """All batches are processed; positional + keyword args reach the
    target unchanged. This is the contract the 9 user_storage fan-out
    callers depend on.
    """
    calls: list[tuple] = []
    lock = threading.Lock()

    def target(batch, provider_id, *, create_groups=False):
        with lock:
            calls.append((tuple(batch), provider_id, create_groups))

    batches = [["u-1", "u-2"], ["u-3"], ["u-4", "u-5", "u-6"]]
    _run_batches_in_pool(target, batches, "prov-1", max_workers=3, create_groups=True)

    assert sorted(calls) == sorted(
        [
            (("u-1", "u-2"), "prov-1", True),
            (("u-3",), "prov-1", True),
            (("u-4", "u-5", "u-6"), "prov-1", True),
        ]
    )


def test_blocks_until_all_batches_complete():
    """Mirrors ``gevent.joinall(jobs)`` semantics: the call must not
    return until every batch finishes. The 9 fan-out callers rely on
    this — they set ``user_storage`` state after the join.
    """
    completed: set[int] = set()
    lock = threading.Lock()

    def target(batch):
        time.sleep(0.05)
        with lock:
            completed.add(batch[0])

    batches = [[i] for i in range(8)]
    _run_batches_in_pool(target, batches, max_workers=4)

    # By the time we get here, every batch must already have completed.
    assert completed == set(range(8))


def test_runs_concurrently_when_workers_allow():
    """Concurrency must be preserved (this is what the gevent fan-out
    bought). Pinning at >1 worker, the wall clock must be roughly
    ``ceil(n_batches / max_workers) * batch_duration`` — if the
    helper accidentally serialised, this assertion would fail.
    """
    barrier = threading.Barrier(parties=4)
    completion_times: list[float] = []
    lock = threading.Lock()

    def target(batch):
        barrier.wait(timeout=2.0)  # 4 workers must reach this concurrently
        with lock:
            completion_times.append(time.monotonic())

    start = time.monotonic()
    batches = [[i] for i in range(4)]
    _run_batches_in_pool(target, batches, max_workers=4)
    elapsed = time.monotonic() - start

    # All 4 hit the barrier within 2 s, so the helper truly ran them
    # in parallel. If it had serialised we would have gotten the
    # barrier timeout (BrokenBarrierError).
    assert len(completion_times) == 4
    # Wall clock should be tight; 1 s is generous against a sequential
    # baseline of barrier_timeout * 4 = 8 s.
    assert elapsed < 1.0


def test_swallows_individual_batch_exceptions():
    """Mirrors ``gevent.joinall(raise_error=False)`` semantics: one
    bad batch must not abort the rest. The fan-out callers do not
    handle per-batch failures upstream.
    """
    completed: list[int] = []
    lock = threading.Lock()

    def target(batch):
        if batch[0] == 1:
            raise RuntimeError("boom")
        with lock:
            completed.append(batch[0])

    batches = [[0], [1], [2]]
    # Must NOT raise.
    _run_batches_in_pool(target, batches, max_workers=3)

    assert sorted(completed) == [0, 2]


def test_empty_batches_is_a_noop():
    """Empty input short-circuits without spawning a pool — matches
    the prior ``if not len(data_batch): return`` guard each caller
    used.
    """
    calls = []

    def target(batch):
        calls.append(batch)

    _run_batches_in_pool(target, [], max_workers=10)
    assert calls == []


def test_spawn_daemon_runs_target_off_caller_thread():
    """``_spawn_daemon`` replaces ``gevent.spawn(target, *args, **kw)``.

    Pins:
    - The target runs (it doesn't sit on an undriven gevent Hub —
      that was the SIGSEGV root cause).
    - It runs on a *different* thread (so the caller doesn't block).
    - It receives positional and keyword args verbatim.
    """
    done_event = threading.Event()
    captured: dict = {}

    def target(user_id, *, role=None):
        captured["thread"] = threading.get_ident()
        captured["user_id"] = user_id
        captured["role"] = role
        done_event.set()

    caller_thread = threading.get_ident()
    thread = _spawn_daemon(target, "u-1", role="admin")
    # The thread is daemon-mode so it doesn't prevent process exit.
    assert thread.daemon is True
    # Target must run within a short window.
    assert done_event.wait(timeout=2.0), "target never ran"
    assert captured["user_id"] == "u-1"
    assert captured["role"] == "admin"
    assert captured["thread"] != caller_thread


def test_spawn_daemon_later_runs_after_delay():
    """``_spawn_daemon_later`` replaces
    ``gevent.spawn_later(delay, target, *args, **kw)``.

    Pins that the target fires after the delay, on a daemon thread.
    """
    done_event = threading.Event()
    captured: dict = {}

    def target(provider_id):
        captured["fired_at"] = time.monotonic()
        captured["provider_id"] = provider_id
        done_event.set()

    start = time.monotonic()
    timer = _spawn_daemon_later(0.1, target, "prov-1")
    assert timer.daemon is True
    assert done_event.wait(timeout=2.0), "delayed target never ran"
    assert captured["provider_id"] == "prov-1"
    elapsed = captured["fired_at"] - start
    assert 0.08 <= elapsed < 1.0, f"expected ~0.1s delay, got {elapsed:.3f}s"


def test_spawn_daemon_later_can_be_cancelled():
    """The returned ``Timer`` must be cancellable so callers that
    want to abort a pending fire (e.g. the WS connection-status
    watcher in ``isard_user_storage_get_providers``) can do so. With
    the prior ``gevent.spawn_later`` callers had no cancellation
    handle at all.
    """
    fired = threading.Event()
    timer = _spawn_daemon_later(0.5, fired.set)
    timer.cancel()
    # Wait past the original delay; the event must NOT fire.
    fired.wait(timeout=0.7)
    assert not fired.is_set()


def test_caps_workers_at_batch_count():
    """When there are fewer batches than ``max_workers``, the pool
    only spawns what's needed. Implementation detail captured here
    because the previous gevent fan-out didn't pre-size; this protects
    against a future refactor that drops the cap.
    """
    seen_threads: set[int] = set()
    lock = threading.Lock()

    def target(batch):
        with lock:
            seen_threads.add(threading.get_ident())

    _run_batches_in_pool(target, [[1], [2]], max_workers=10)
    # At most 2 distinct worker threads (one per batch); often 1 if
    # the second submit landed before the first completed and the
    # ThreadPoolExecutor reused the worker. The contract is "≤ batch
    # count," not "= batch count."
    assert 1 <= len(seen_threads) <= 2
