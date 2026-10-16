# SPDX-License-Identifier: AGPL-3.0-or-later

"""The free-space floor must hold from the very first tick of a window.

At a recurring job's window opening the job is ``scheduled`` and, between
occurrences, every item is settled, so the floor check that runs before the
re-scan saw a "complete, idle" job and let the freshly re-armed trees start.
The storage worker then refused the copy ("refusing to copy ... below the
... byte floor"), the disk went ``failed`` and, three nights running, a healthy
disk ended ``quarantined`` for a reason that was never about the disk.
"""

from datetime import datetime

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import MigrationStatus

from .test_migration_recurring_drive import WINDOW, _item, _Mig, _runner

NOW = datetime(2026, 7, 1, 12, 0)
REFUSAL = (
    "RuntimeError: move: refusing to copy /isard/storage_pools/cold/c/groups/n.qcow2: "
    "destination /isard/storage_pools/hot/c/groups would be left with 11039003172864 "
    "bytes free, below the 15000000000000 byte floor (filesystem-level figure)"
)


def _recurring(status, **cfg):
    m = _Mig(
        status,
        {
            "recurring": True,
            "rescan_cadence": "edge",
            "window": WINDOW,
            "min_free_bytes": 50,
            "parallelism": 2,
            **cfg,
        },
    )
    m.logs = []
    m.pause_reason = None
    m.space_probe = {}
    return m


def test_window_opening_below_the_floor_starts_no_tree(monkeypatch):
    """Scheduled job, previous occurrence settled, new disk re-scanned in:
    nothing may be dispatched while the destination is under the floor."""
    items = [_item("r", "released")]
    planned = [_item("n", "pending", tree="n")]
    m = _recurring(MigrationStatus.SCHEDULED.value)
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.free_space_fn = lambda: (20, 100)  # 20 bytes free < 50 floor
    result = r.tick()
    started = [a for (_t, _i, a) in result if a == "start_preflight"]
    assert started == []
    assert all(it["state"] in ("released", "pending") for it in items)
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "space"


def test_budget_parked_job_reopening_below_the_floor_starts_no_tree(monkeypatch):
    """A job left budget_reached with pending trees reopens next night already
    holding pending items: same rule."""
    items = [_item("r", "released"), _item("n", "pending", tree="n")]
    m = _recurring(MigrationStatus.BUDGET_REACHED.value)
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=[items[1]])
    r.free_space_fn = lambda: (20, 100)
    result = r.tick()
    assert [a for (_t, _i, a) in result if a == "start_preflight"] == []
    assert items[1]["state"] == "pending"


def test_window_opening_above_the_floor_starts_trees(monkeypatch):
    """Control: with room, the same opening dispatches."""
    items = [_item("r", "released")]
    planned = [_item("n", "pending", tree="n")]
    m = _recurring(MigrationStatus.SCHEDULED.value)
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.free_space_fn = lambda: (80, 100)
    result = r.tick()
    assert ("n", "m--n", "start_preflight") in result


def test_a_worker_floor_refusal_defers_instead_of_failing(monkeypatch):
    """The worker is the last guard. Its refusal means "no room yet", not
    "this disk is bad": the disk goes back to pending, its failure streak is
    untouched, and the job pauses for space."""
    items = [
        _item("n", "moving", tree="n", move_task_id="t1", dst_owned=True),
        _item("o", "pending", tree="o"),
    ]
    m = _recurring(MigrationStatus.RUNNING.value)
    m.last_occurrence = "2026-07-01"
    r = _runner(
        monkeypatch,
        items,
        m,
        now=NOW,
        planned=list(items),
        job_status_fn=lambda tid: "failed" if tid == "t1" else None,
    )
    r.free_space_fn = lambda: (80, 100)
    r._failure_reason = lambda item: REFUSAL
    r._discard_destination = lambda item: (_ for _ in ()).throw(
        AssertionError("nothing was copied: nothing to discard")
    )
    r.tick()
    n = items[0]
    assert n["state"] == "pending"
    assert n.get("move_task_id") is None
    assert int(n.get("occurrence_failures") or 0) == 0
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "space"
    assert items[1]["state"] == "pending"  # no new tree started after the refusal


def test_a_real_move_failure_still_fails(monkeypatch):
    """Control: any other move error keeps terminalizing the tree."""
    items = [_item("n", "moving", tree="n", move_task_id="t1", dst_owned=True)]
    m = _recurring(MigrationStatus.RUNNING.value)
    m.last_occurrence = "2026-07-01"
    r = _runner(
        monkeypatch,
        items,
        m,
        now=NOW,
        planned=list(items),
        job_status_fn=lambda tid: "failed",
    )
    r.free_space_fn = lambda: (80, 100)
    r._failure_reason = lambda item: "RuntimeError: rsync exited 23"
    r._discard_destination = lambda item: None
    r.tick()
    assert items[0]["state"] == "failed"


def test_space_refusal_is_recognised_only_for_the_floor_sentence():
    assert mig.is_space_floor_refusal(REFUSAL)
    assert not mig.is_space_floor_refusal("RuntimeError: rsync exited 23")
    assert not mig.is_space_floor_refusal(None)
    assert not mig.is_space_floor_refusal(
        "RuntimeError: move: refusing to copy /x: cannot size the source"
    )
