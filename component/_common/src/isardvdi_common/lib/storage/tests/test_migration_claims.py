# SPDX-License-Identifier: AGPL-3.0-or-later

"""Stage-1 correctness-core tests.

The reconciler gains atomic ledger *claims* so single-writer-per-disk is enforced
by the ledger (not by who calls the reconciler), making it safe to drive a
migration from more than one place (the edge-triggered orchestrator + the
scheduler backstop). These tests pin the load-bearing properties with mocks (no
DB/redis): a driver that LOSES a claim never submits a second storage job; the
fresh/resume fences are correct; the abandon counter is atomic; ``check_abandon``
gates dead-worker detection; and ``advance()`` guards + lock discipline hold.

The exactly-one-winner property of the real RethinkDB ``claim`` CAS under genuine
concurrency is exercised as a live integration test on the staging box (two
threads, ``LOCK_TTL`` forced tiny), not here.
"""

import isardvdi_common.lib.storage.migration_run as mr
import pytest
from isardvdi_common.models.storage_migration import (
    MigrationItemState,
    StorageMigrationItem,
)


def _runner():
    return object.__new__(mr.MigrationRunner)


# --------------------------------------------------------------------------- #
# _start_move — the one genuinely-corrupting double-submit (two rsyncs -> 1 dst)
# --------------------------------------------------------------------------- #
def _move_runner(monkeypatch, item, *, claim_result):
    caps = {"enqueued": 0, "claims": []}

    def _claim(cls, item_id, *, when, set_fields):
        caps["claims"].append((dict(when), dict(set_fields)))
        if claim_result:
            item.update(set_fields)
        return claim_result

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))
    monkeypatch.setattr(
        mr.StorageMigrationItem, "incr", classmethod(lambda cls, iid, f, by=1: 1)
    )

    class _S:
        def __init__(self, sid):
            self.status = "ready"

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _S)

    r = _runner()
    r.config = {}
    r.user_id = "admin"

    def _enq(*a, **k):
        caps["enqueued"] += 1
        return "real-tid"

    r._enqueue = _enq
    r._move_queue = lambda p: "q"
    r._set = lambda it, **f: it.update(f)
    return r, caps


def test_start_move_lost_claim_never_submits_rsync(monkeypatch):
    """THE safety property: a driver that loses the atomic claim must not enqueue
    a second rsync onto the same destination file."""
    item = {
        "id": "i1",
        "state": "pending",
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": None,
    }
    r, caps = _move_runner(monkeypatch, item, claim_result=False)
    r._start_move(item)
    assert caps["enqueued"] == 0
    assert caps["claims"][0][0] == {"state": "pending"}  # claimed on fresh state


def test_start_move_won_claim_fences_then_submits_once(monkeypatch):
    item = {
        "id": "i1",
        "state": "pending",
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": None,
    }
    r, caps = _move_runner(monkeypatch, item, claim_result=True)
    r._start_move(item)
    assert caps["enqueued"] == 1
    when, sf = caps["claims"][0]
    # fresh claim flips pending->moving AND reserves a fenced task id atomically,
    # so state==moving ALWAYS carries a task id (no unresumable wedge).
    assert when == {"state": "pending"}
    assert sf["state"] == MigrationItemState.MOVING.value
    assert sf["move_task_id"].startswith("claim:")
    # the real task id replaces the fence after a successful enqueue
    assert item["move_task_id"] == "real-tid"
    assert item["state"] == MigrationItemState.MOVING.value


def _stateaware_move_runner(monkeypatch, item):
    """A move runner whose claim mock evaluates the when-clause against the live
    item dict (faithful CAS), so a state guard that no longer holds loses."""
    caps = {"enqueued": 0, "incr_calls": 0}

    def _claim(cls, item_id, *, when, set_fields):
        if all(item.get(k) == v for k, v in when.items()):
            item.update(set_fields)
            return True
        return False

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))

    def _incr(cls, iid, f, by=1):
        caps["incr_calls"] += 1
        item[f] = int(item.get(f) or 0) + by
        return item[f]

    monkeypatch.setattr(mr.StorageMigrationItem, "incr", classmethod(_incr))

    class _S:
        def __init__(self, sid):
            self.status = "ready"

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _S)
    r = _runner()
    r.config = {}
    r.user_id = "admin"

    def _enq(*a, **k):
        caps["enqueued"] += 1
        return "real-tid"

    r._enqueue = _enq
    r._move_queue = lambda p: "q"
    r._set = lambda it, **f: it.update(f)
    return r, caps


def test_start_move_resume_wrong_state_loses(monkeypatch):
    """The resume state guard: an item that ALREADY advanced out of moving (a
    concurrent driver did _mark_moved: state=moved, move_task_id unchanged) must
    NOT be re-claimed back to moving -- the stale resume claim fails, no rsync."""
    item = {
        "id": "i1",
        "state": "moved",  # advanced out of moving; move_task_id still set
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": "gone-tid",
    }
    r, caps = _stateaware_move_runner(monkeypatch, item)
    r._start_move(item)
    assert caps["enqueued"] == 0  # claim lost -> no regression to moving
    assert item["state"] == "moved"  # unchanged
    assert item["move_task_id"] == "gone-tid"


def test_start_move_fence_resume_not_charged_to_abandon(monkeypatch):
    """A crash between claim and enqueue leaves move_task_id='claim:...'. Re-driving
    that fence is a scheduler-crash resume, NOT a worker death -> it must not spend
    the MAX_ABANDON_RESTARTS budget (no incr call)."""
    item = {
        "id": "i1",
        "state": "moving",
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": "claim:deadbeef",  # a fence, never enqueued
    }
    r, caps = _stateaware_move_runner(monkeypatch, item)
    r._start_move(item)
    assert caps["enqueued"] == 1  # re-fenced and enqueued
    assert caps["incr_calls"] == 0  # fence resume NOT charged to abandon budget


def test_start_move_real_resume_is_charged_to_abandon(monkeypatch):
    """Contrast: a REAL gone task id (worker died) DOES spend the abandon budget."""
    item = {
        "id": "i1",
        "state": "moving",
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": "real-gone-tid",
    }
    r, caps = _stateaware_move_runner(monkeypatch, item)
    r._start_move(item)
    assert caps["enqueued"] == 1
    assert caps["incr_calls"] == 1  # genuine abandonment counted


def test_start_move_resume_fences_the_observed_task_id(monkeypatch):
    """A RESUME (move_task_id set, job gone) fences the OBSERVED id, so exactly one
    of two racing drivers re-enqueues."""
    item = {
        "id": "i1",
        "state": "moving",
        "storage_id": "s1",
        "src_path": "/a",
        "dst_path": "/b",
        "move_task_id": "gone-tid",
    }
    r, caps = _move_runner(monkeypatch, item, claim_result=True)
    r._start_move(item)
    when, sf = caps["claims"][0]
    # resume guards BOTH the dispatching state (moving) AND the observed task id,
    # matching _start_rebase/_start_verify: a concurrent advance out of moving
    # (moved/failed/skipped, which leave move_task_id unchanged) makes this fail
    # rather than regressing the disk back to moving.
    assert when == {"state": "moving", "move_task_id": "gone-tid"}
    assert sf["move_task_id"].startswith("claim:")
    assert caps["enqueued"] == 1


# --------------------------------------------------------------------------- #
# _start_rebase / _start_verify — idempotent tasks, still claim-gated
# --------------------------------------------------------------------------- #
def _simple_runner(monkeypatch, *, claim_result):
    caps = {"enqueued": 0, "claims": []}

    def _claim(cls, item_id, *, when, set_fields):
        caps["claims"].append((dict(when), dict(set_fields)))
        return claim_result

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))
    r = _runner()
    r.config = {}
    r.user_id = "admin"

    def _enq(*a, **k):
        caps["enqueued"] += 1
        return "real-tid"

    r._enqueue = _enq
    r._pool_queue = lambda p: "q"
    r._set = lambda it, **f: it.update(f)
    return r, caps


def test_start_rebase_lost_claim_no_enqueue(monkeypatch):
    item = {
        "id": "i1",
        "state": "moved",
        "rebase_task_id": None,
        "dst_path": "/b",
        "parent_dst_path": "/pb",
    }
    r, caps = _simple_runner(monkeypatch, claim_result=False)
    r._start_rebase(item)
    assert caps["enqueued"] == 0
    assert caps["claims"][0][0] == {"state": "moved", "rebase_task_id": None}


def test_start_verify_lost_claim_no_enqueue(monkeypatch):
    item = {
        "id": "i1",
        "state": "rebased",
        "verify_task_id": None,
        "dst_path": "/b",
        "parent_dst_path": "/pb",
    }
    r, caps = _simple_runner(monkeypatch, claim_result=False)
    r._start_verify(item)
    assert caps["enqueued"] == 0
    assert caps["claims"][0][0] == {"state": "rebased", "verify_task_id": None}


def test_start_verify_won_claim_enqueues_once(monkeypatch):
    item = {
        "id": "i1",
        "state": "rebased",
        "verify_task_id": None,
        "dst_path": "/b",
        "parent_dst_path": "/pb",
    }
    r, caps = _simple_runner(monkeypatch, claim_result=True)
    r._start_verify(item)
    assert caps["enqueued"] == 1
    assert item["verify_task_id"] == "real-tid"


# --------------------------------------------------------------------------- #
# atomic abandon counter
# --------------------------------------------------------------------------- #
def test_abandon_resume_blocked_uses_atomic_incr(monkeypatch):
    """The bound is decided by the atomic incr's RETURN value (not a
    read-modify-write), so a lost update can't defeat MAX_ABANDON_RESTARTS."""
    calls = {"incr": 0}

    def _incr(cls, iid, field, by=1):
        calls["incr"] += 1
        return calls["incr"]  # 1,2,3,...

    monkeypatch.setattr(mr.StorageMigrationItem, "incr", classmethod(_incr))
    r = _runner()
    item = {"id": "i1", "tree_id": "t", "abandon_restarts": 0}
    # first calls are under budget -> not blocked
    assert r._abandon_resume_blocked(item) is False
    assert item["abandon_restarts"] == 1
    for _ in range(mr.MAX_ABANDON_RESTARTS - 1):
        assert r._abandon_resume_blocked(item) is False
    # the (MAX+1)th increment trips the bound -> blocked + terminalize
    r._terminalize_tree_failure = lambda it: calls.__setitem__("terminalized", True)
    assert r._abandon_resume_blocked(item) is True
    assert calls.get("terminalized") is True


# --------------------------------------------------------------------------- #
# check_abandon gate on job_status
# --------------------------------------------------------------------------- #
def test_job_status_check_abandon_gate(monkeypatch):
    class _T:
        def __init__(self, tid):
            pass

        @classmethod
        def exists(cls, tid):
            return True

        exc_info = None
        job_status = "started"
        result = None

    monkeypatch.setattr(mr, "Task", _T)
    seen = {"abandon": 0}

    def _ab(task):
        seen["abandon"] += 1
        return True

    monkeypatch.setattr(mr, "_job_abandoned", _ab)
    # edge path: never consult abandon -> a live-but-starved STARTED passes through
    assert mr.job_status("t", check_abandon=False) == "started"
    assert seen["abandon"] == 0
    # backstop path: an abandoned STARTED job is reported GONE (None) -> resume
    assert mr.job_status("t", check_abandon=True) is None
    assert seen["abandon"] == 1


# --------------------------------------------------------------------------- #
# advance() — guards + gevent-safe lock discipline
# --------------------------------------------------------------------------- #
def _fake_migration(monkeypatch, *, exists, status):
    class _M:
        @classmethod
        def exists(cls, mid):
            return exists

        def __init__(self, mid):
            self.status = status

    monkeypatch.setattr(mr, "StorageMigration", _M)


def test_advance_gone_when_missing(monkeypatch):
    _fake_migration(monkeypatch, exists=False, status="running")
    assert mr.advance("m") == "gone"


def test_advance_not_drivable_when_terminal(monkeypatch):
    _fake_migration(monkeypatch, exists=True, status="completed")
    assert mr.advance("m") == "not_drivable"


def _fake_lock(events, *, acquire=True, reacquire=None):
    class _Lock:
        def acquire(self):
            events.append("acquire")
            return acquire

        def reacquire(self):
            events.append("reacquire")
            if reacquire == "raise":
                raise mr.LockError("lost")
            return True

        def release(self):
            events.append("release")

    class _Conn:
        def lock(self, *a, **k):
            return _Lock()

        def close(self):
            pass

    return _Conn()


def test_advance_busy_when_lock_held(monkeypatch):
    _fake_migration(monkeypatch, exists=True, status="running")
    monkeypatch.setattr(
        mr.redis, "from_url", lambda *a, **k: _fake_lock([], acquire=False)
    )
    assert mr.advance("m") == "busy"


def test_advance_drains_and_releases(monkeypatch):
    _fake_migration(monkeypatch, exists=True, status="running")
    events = []
    monkeypatch.setattr(mr.redis, "from_url", lambda *a, **k: _fake_lock(events))

    class _Runner:
        def __init__(self, mid, *, job_status_fn):
            pass

        def tick(self):
            return []  # no progress -> drain breaks after one iteration

        def is_complete(self):
            return False

    monkeypatch.setattr(mr, "MigrationRunner", _Runner)
    assert mr.advance("m") == "done"
    # reacquire (watchdog) runs at the TOP of the loop, release in finally
    assert events == ["acquire", "reacquire", "release"]


def test_claim_rejects_empty_when():
    """An empty `when` would make r.and_() true and degrade the CAS to an
    unconditional write (every caller "wins"). The model guards it BEFORE any DB
    access, so this raises without a connection."""
    with pytest.raises(ValueError):
        StorageMigrationItem.claim("i1", when={}, set_fields={"state": "moving"})


def test_advance_aborts_and_releases_on_lost_lease(monkeypatch):
    _fake_migration(monkeypatch, exists=True, status="running")
    events = []
    monkeypatch.setattr(
        mr.redis, "from_url", lambda *a, **k: _fake_lock(events, reacquire="raise")
    )

    class _Runner:
        def __init__(self, mid, *, job_status_fn):
            pass

        def tick(self):
            raise AssertionError("tick must not run after the lease is lost")

        def is_complete(self):
            return False

    monkeypatch.setattr(mr, "MigrationRunner", _Runner)
    # lost lease at the top of the loop -> abort BEFORE mutating, still release,
    # and report "aborted" (distinct from a clean "done") so an edge caller re-wakes
    assert mr.advance("m") == "aborted"
    assert events == ["acquire", "reacquire", "release"]
