# SPDX-License-Identifier: AGPL-3.0-or-later

"""The per-event migration driver must not loop on a space-deferred disk, and a
cancel with only not-started trees left must reach ``canceled`` without waiting
for the window.

Three defects, all in the per-event path (the full pass ``tick`` already handles
each shape correctly; these exercise ``drive_trees`` / ``needs_full_pass`` / the
admission gate):

* T1/T2 — a disk the worker refused for space is put back to ``pending`` but its
  single-disk tree is LEFT in ``drive.active``; ``drive_trees`` then re-steps it
  (``_start_move`` again) without looking at the space pause or the window, so the
  worker refuses again every pass. The parked tree must leave ``drive.active`` and
  go back to the head of the frozen order instead, and no move may be enqueued
  until a legitimate resume.
* T3 — on cancel (``finishing_tree``) with ``drive.active`` empty and an unstarted
  tree frozen in ``migration:order:<id>``, ``needs_full_pass`` returns False (the
  list is not empty) and ``drive_trees`` admits nothing (``_admit`` is skipped
  under cancel), so the job wedges in ``finishing_tree`` until the window opens.
* T4 — the engine resumes/admits when ``free >= min_free_bytes`` but the worker
  reserves the disk too (``free - needed < min_free_bytes``), so it relaunches a
  move the worker is certain to refuse. The engine must reserve the same bytes.
"""

import pytest
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import MigrationStatus

from .test_migration_drive_events import ORDER, _Lock, _scripted_saga
from .test_migration_recurring_drive import (
    NOW,
    WINDOW,
    _FakeRedis,
    _item,
    _Mig,
    _runner,
)

# A window that is CLOSED at NOW (Wed 2026-07-01 12:00); WINDOW (09:00-17:00) is open.
WINDOW_CLOSED = {"start": "20:00", "end": "22:00", "days": [], "tz": "UTC"}


def _space_runner(
    monkeypatch,
    items,
    *,
    active,
    order,
    window,
    window_open,
    free,
    min_free_bytes=100,
    parallelism=1,
):
    """A space-paused job over an in-memory ledger: ``drive.active`` / order list /
    free-space reading are the knobs the three defects turn on. ``_ACTIONS`` only
    flips a disk to ``moving`` so a re-started move shows up as a state change."""
    m = _Mig(
        "paused",
        {
            "parallelism": parallelism,
            "min_free_bytes": min_free_bytes,
            "window": window,
        },
    )
    m.pause_reason = "space"
    m.last_occurrence = "2026-07-01"
    m.logs = []
    m.space_probe = {}
    m.drive = {"active": list(active), "window_open": window_open, "drained": False}
    m.record_activity = lambda delta=None: None
    r = _runner(
        monkeypatch, items, m, now=NOW, job_status_fn=_scripted_saga(monkeypatch, set())
    )
    redis = _FakeRedis()
    if order:
        redis.rpush(ORDER, *order)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")
    moved = []

    def _start(self, item):
        moved.append(item["storage_id"])
        self._set(item, state="moving", move_task_id=f"t-{item['storage_id']}")

    def _finish(self, item):
        self._set(item, state="released")

    r._ACTIONS = {"start": _start, "finish": _finish}
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "tree_rows",
        classmethod(lambda cls, mid, tid: [it for it in items if it["tree_id"] == tid]),
    )
    r.prepare = lambda tree_items=None: None
    r.reactivate = lambda tree_items=None: None
    r.free_space_fn = lambda: free
    return r, m, redis, moved


# --------------------------------------------------------------------------- #
# T1 — space pause, window CLOSED: the parked tree leaves active, nothing moves
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("call", ["per_event", "periodic"])
def test_t1_space_deferred_tree_is_parked_not_re_driven(monkeypatch, call):
    # "a" was refused for space and is back to pending, but still sits in active.
    items = [_item("a", "pending", tree="a")]
    r, m, redis, moved = _space_runner(
        monkeypatch,
        items,
        active=["a"],
        order=["b"],
        window=WINDOW_CLOSED,
        window_open=False,
        free=(50, 1000),  # below the 100 floor (window closed -> not even read)
    )

    r.drive_trees(["a"] if call == "per_event" else None)

    assert moved == []  # no move enqueued
    assert items[0]["state"] == "pending"  # the disk was not re-started
    assert m.drive["active"] == []  # the parked tree left drive.active
    assert redis.lists[ORDER] == ["a", "b"]  # and went back to the HEAD of the order
    assert m.status == MigrationStatus.PAUSED.value and m.pause_reason == "space"


# --------------------------------------------------------------------------- #
# T2 — space pause, window OPEN, still below the floor: no move until a resume
# --------------------------------------------------------------------------- #
def test_t2_open_window_still_below_floor_parks_and_does_not_move(monkeypatch):
    items = [_item("a", "pending", tree="a")]
    r, m, redis, moved = _space_runner(
        monkeypatch,
        items,
        active=["a"],
        order=[],
        window=WINDOW,
        window_open=True,
        free=(50, 1000),  # 50 < 100 floor -> still breached, must not resume
    )

    r.drive_trees(None)

    assert moved == []
    assert items[0]["state"] == "pending"
    assert m.drive["active"] == []
    assert redis.lists[ORDER] == ["a"]
    assert m.status == MigrationStatus.PAUSED.value and m.pause_reason == "space"


def test_t2_a_legitimate_resume_moves_the_parked_disk(monkeypatch):
    # the floor truly clears with room for the disk -> the disk moves again
    items = [_item("a", "pending", tree="a", size_bytes=10)]
    r, m, redis, moved = _space_runner(
        monkeypatch,
        items,
        active=[],  # already parked in a prior pass
        order=["a"],
        window=WINDOW,
        window_open=True,
        free=(500, 1000),  # 500 - 10 = 490 >= 100 floor -> fits
    )

    r.drive_trees(None)

    assert moved == ["a"]  # admitted and started
    assert items[0]["state"] == "moving"
    assert m.status == MigrationStatus.RUNNING.value


# --------------------------------------------------------------------------- #
# T3 — cancel with a not-started tree frozen in the order list reaches canceled
# --------------------------------------------------------------------------- #
def test_t3_needs_full_pass_when_a_cancel_has_waiting_trees(monkeypatch):
    # finishing_tree, nothing in flight, a not-started tree still in the order list,
    # window CLOSED (so no window-open edge forces the pass): only a full pass can
    # skip it and complete, so one is due.
    m = _Mig("finishing_tree", {"window": WINDOW_CLOSED})
    m.last_occurrence = "2026-07-01"
    m.drive = {"active": [], "window_open": False, "finishing": True, "drained": False}
    r = _runner(monkeypatch, [], m, now=NOW)
    redis = _FakeRedis()
    redis.rpush(ORDER, "a")
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")

    assert r.needs_full_pass() is True


def test_t3_cancel_with_a_waiting_tree_reaches_canceled_without_the_window(monkeypatch):
    items = [_item("a", "pending", tree="a")]
    m = _Mig("finishing_tree", {"window": WINDOW_CLOSED})  # window CLOSED at NOW
    m.last_occurrence = "2026-07-01"
    m.logs = []
    m.drive = {"active": [], "window_open": False, "finishing": True, "drained": False}
    r = _runner(monkeypatch, items, m, now=NOW)
    redis = _FakeRedis()
    redis.rpush(ORDER, "a")
    redis.lock = lambda *a, **k: _Lock(True)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "tree_rows",
        classmethod(lambda cls, mid, tid: [it for it in items if it["tree_id"] == tid]),
    )

    class _SM:
        exists = staticmethod(lambda mid: True)

        def __new__(cls, mid):
            return m

        @classmethod
        def update_document_if(
            cls,
            doc_id,
            update_data,
            *,
            field,
            values=None,
            excluding=None,
            validate=True,
        ):
            # same CAS as _patch_status_claim, which this _SM replaced
            held = m.live.get(field)
            if (values is not None and held not in values) or (
                excluding is not None and held in excluding
            ):
                return False
            m.live.update(update_data)
            for key, value in update_data.items():
                object.__setattr__(m, key, value)
            return True

    monkeypatch.setattr(mr, "StorageMigration", _SM)
    monkeypatch.setattr(mr, "MigrationRunner", lambda mid, *, job_status_fn: r)
    monkeypatch.setattr(mr, "job_status", lambda *a, **k: None)

    mr.advance("m", check_abandon=False)

    assert items[0]["state"] == "skipped"  # the not-started tree was skipped
    assert m.live["status"] == "canceled"  # reached canceled without the window
    assert redis.llen(ORDER) == 0  # the order list was drained


# --------------------------------------------------------------------------- #
# T4 — within the window, free is above the floor but the next disk does not fit
# --------------------------------------------------------------------------- #
def test_t4_does_not_relaunch_a_move_the_worker_would_refuse(monkeypatch):
    # free == floor: space_floor_breached is False (the engine would resume), but
    # the worker reserves the disk's size, so free - size < floor -> it refuses.
    # The engine must reserve the same bytes and NOT relaunch.
    items = [_item("a", "pending", tree="a", size_bytes=30)]
    r, m, redis, moved = _space_runner(
        monkeypatch,
        items,
        active=[],
        order=["a"],
        window=WINDOW,
        window_open=True,
        free=(100, 1000),  # 100 >= 100 floor, but 100 - 30 = 70 < 100
        min_free_bytes=100,
    )

    r.drive_trees(None)

    assert moved == []  # no doomed move enqueued
    assert items[0]["state"] == "pending"
    assert redis.lists[ORDER] == ["a"]  # the disk kept its place
    # it did not log a resume it immediately had to take back
    assert not any(e["event"] == "resumed_min_free" for e in m.logs)
