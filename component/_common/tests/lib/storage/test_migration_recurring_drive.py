# SPDX-License-Identifier: AGPL-3.0-or-later

"""Runner-level tests for the recurring DRIVE wiring in ``MigrationRunner.tick``
(the pure decisions are covered in test_migration_rescan / _recurring_status).

These exercise the wiring against an in-memory ledger with the Storage / redis /
enqueue boundaries stubbed:
  * a recurring job that has drained goes to ``scheduled`` (never ``completed``),
  * an occurrence-edge re-scan re-arms the prior occurrence's failed disks (and
    inserts newly-matching ones), quarantining under ``retry_quarantine`` once the
    budget is hit,
  * ``failure_policy=pause`` moves the job to ``paused`` on a disk failure.
"""

from datetime import datetime

import pytest
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import MigrationStatus


class _Mig:
    def __init__(self, status, config, selection=None):
        self.status = status
        self.config = config
        self.selection = selection or {"kind": "pool", "dst_pool_id": "dst"}
        self.current_window = None
        self.last_occurrence = None
        self.throughput_ewma = {}

    def recompute_totals(self):
        pass


def _item(sid, state, tree="r", **kw):
    base = {
        "id": f"m--{sid}",
        "migration_id": "m",
        "storage_id": sid,
        "tree_id": tree,
        "topo_index": 0 if sid == tree else 1,
        "state": state,
        "size_bytes": 10,
        "src_path": f"/src/{sid}.qcow2",
        "dst_path": f"/dst/{sid}.qcow2",
        "occurrence_failures": 0,
        "audit": [],
        "parent_dst_path": None if sid == tree else "/dst/r.qcow2",
    }
    base.update(kw)
    return base


def _runner(
    monkeypatch, items, mig_obj, *, now, planned=None, job_status_fn=lambda t: None
):
    """A MigrationRunner over the in-memory ``items`` list; Storage / redis /
    enqueue / re-plan boundaries stubbed. ``now`` is the datetime the runner sees;
    ``planned`` is what a re-scan resolves to (defaults to the current items)."""
    monkeypatch.setattr(
        mr.StorageMigrationItem, "dicts_by_migration", classmethod(lambda cls, m: items)
    )

    def _update(cls, iid, fields, validate=True):
        for it in items:
            if it["id"] == iid:
                it.update(fields)

    monkeypatch.setattr(
        mr.StorageMigrationItem, "update_document", classmethod(_update)
    )

    def _claim(cls, item_id, *, when, set_fields):
        for it in items:
            if it["id"] == item_id:
                if all(it.get(k) == v for k, v in when.items()):
                    it.update(set_fields)
                    return True
                return False
        return False

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))

    def _incr(cls, item_id, field, by=1):
        for it in items:
            if it["id"] == item_id:
                it[field] = int(it.get(field) or 0) + by
                return it[field]
        return None

    monkeypatch.setattr(mr.StorageMigrationItem, "incr", classmethod(_incr))
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "upsert",
        classmethod(lambda cls, data: items.append(data)),
    )
    monkeypatch.setattr(
        mig,
        "roots_for_selection",
        lambda sel: sorted(
            {it["tree_id"] for it in (planned if planned is not None else items)}
        ),
    )
    monkeypatch.setattr(
        mig,
        "build_plan_for_roots",
        lambda mid, roots, pool, **k: ((planned if planned is not None else []), {}),
    )

    class _Storage:
        def __init__(self, sid):
            self.status = "ready"

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _Storage)

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = mig_obj
    r.config = mig_obj.config
    r.user_id = "admin"
    r.dst_pool = None
    r.job_status_fn = job_status_fn
    r._now = lambda tz: now
    r._domains = lambda sid: []
    r._publish_progress = lambda: None
    r.prepare = lambda: None
    r.reactivate = lambda: None
    r._enqueue = lambda *a, **k: "tid"
    r._pool_queue = lambda p, action: "q"
    r._move_queue = lambda p: "q"
    r._pool_of = lambda p: type("P", (), {"id": "p"})()
    r._admit_tree = lambda *a, **k: True
    r._restore_storage_status = lambda it: None
    return r


# A window open now on the current weekday (Wed 2026-07-01 12:00, days=[]).
NOW = datetime(2026, 7, 1, 12, 0)
WINDOW = {"start": "09:00", "end": "17:00", "days": [], "tz": "UTC"}


def test_recurring_complete_goes_scheduled(monkeypatch):
    items = [_item("r", "released")]
    m = _Mig("running", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"})
    m.last_occurrence = "2026-07-01"  # already scanned this occurrence
    r = _runner(monkeypatch, items, m, now=NOW)
    r.tick()
    assert m.status == MigrationStatus.SCHEDULED.value  # NOT completed


def test_recurring_occurrence_edge_rearms_failed(monkeypatch):
    # a failed disk from a prior occurrence is re-armed to pending on a new edge
    items = [_item("r", "failed", occurrence_failures=1)]
    planned = [_item("r", "pending")]  # re-plan still sees it in scope
    m = _Mig(
        "scheduled",
        {
            "recurring": True,
            "window": WINDOW,
            "rescan_cadence": "edge",
            "failure_policy": "retry_quarantine",
            "quarantine_after": 3,
        },
    )
    m.last_occurrence = "2026-06-30"  # DIFFERENT -> fresh occurrence edge
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    # re-armed off the terminal `failed` state (the tick then starts moving it),
    # with the consecutive-occurrence streak incremented and the edge recorded.
    assert items[0]["state"] != "failed"
    assert items[0]["occurrence_failures"] == 2
    assert m.last_occurrence == "2026-07-01"


def test_recurring_quarantines_after_budget(monkeypatch):
    # occurrence_failures already 2; a 3rd occurrence failure hits quarantine_after=3
    items = [_item("r", "failed", occurrence_failures=2)]
    planned = [_item("r", "pending")]
    m = _Mig(
        "scheduled",
        {
            "recurring": True,
            "window": WINDOW,
            "rescan_cadence": "edge",
            "failure_policy": "retry_quarantine",
            "quarantine_after": 3,
        },
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert items[0]["state"] == "quarantined"
    assert items[0]["occurrence_failures"] == 3
    # a quarantined disk is audited
    assert any(a["result"] == "quarantined" for a in items[0]["audit"])


def test_retry_forever_never_quarantines(monkeypatch):
    items = [_item("r", "failed", occurrence_failures=99)]
    planned = [_item("r", "pending")]
    m = _Mig(
        "scheduled",
        {
            "recurring": True,
            "window": WINDOW,
            "rescan_cadence": "edge",
            "failure_policy": "retry_forever",
            "quarantine_after": 3,
        },
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert items[0]["state"] != "quarantined"  # re-armed, never quarantined
    assert items[0]["state"] != "failed"
    assert items[0]["occurrence_failures"] == 100


def test_pause_policy_pauses_on_failure(monkeypatch):
    # a disk whose move task FAILED, policy=pause -> job goes paused this tick
    items = [_item("r", "moving", move_task_id="mt")]
    m = _Mig(
        "running",
        {
            "recurring": True,
            "window": WINDOW,
            "rescan_cadence": "edge",
            "failure_policy": "pause",
        },
    )
    m.last_occurrence = "2026-07-01"  # same occurrence -> no rescan interference
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "failed")
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert items[0]["state"] == "failed"  # tree terminalized


# --------------------------------------------------------------------------- #
# free-space floor (min_free_pct): pause a running job whose destination is full
# --------------------------------------------------------------------------- #
def test_min_free_pct_pauses_running_job(monkeypatch):
    items = [_item("r", "pending")]
    m = _Mig("running", {"min_free_pct": 50, "window": WINDOW})
    m.last_occurrence = "2026-07-01"  # same occurrence -> no rescan interference
    m.logs = []
    m.space_probe = {"free_bytes": 5, "total_bytes": 100}
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (5, 100)  # 5% free, below the 50% floor
    result = r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert items[0]["state"] == "pending"  # returned before any move was enqueued
    assert any(e["event"] == "paused_min_free" for e in m.logs)
    assert result == [("__space__", None, "paused_min_free")]


def test_min_free_pct_ok_does_not_pause(monkeypatch):
    items = [_item("r", "pending")]
    m = _Mig("running", {"min_free_pct": 10, "window": WINDOW})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (80, 100)  # 80% free, above the 10% floor
    assert r._space_floor_breached() is False


def test_min_free_pct_unknown_reading_does_not_pause(monkeypatch):
    items = [_item("r", "pending")]
    m = _Mig("running", {"min_free_pct": 90, "window": WINDOW})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: None  # probe not ready yet -> fail open
    assert r._space_floor_breached() is False


def test_min_free_pct_completed_job_not_paused(monkeypatch):
    items = [_item("r", "released")]  # nothing left to protect
    m = _Mig("running", {"min_free_pct": 90, "window": WINDOW})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (1, 100)
    assert r._space_floor_breached() is False


def test_no_floor_configured_skips_probe(monkeypatch):
    items = [_item("r", "pending")]
    m = _Mig("running", {"window": WINDOW})  # no min_free_pct / min_free_bytes

    def _boom():
        raise AssertionError("free_space_fn must not be called when no floor is set")

    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = _boom
    assert r._space_floor_breached() is False


# --------------------------------------------------------------------------- #
# a pause for space resumes by itself once the destination clears the floor
# --------------------------------------------------------------------------- #
def _space_paused(config, **kw):
    m = _Mig("paused", {"window": WINDOW, **config}, **kw)
    m.pause_reason = "space"
    m.last_occurrence = "2026-07-01"
    m.logs = []
    m.space_probe = {}
    return m


def test_space_pause_is_tagged_as_space(monkeypatch):
    items = [_item("r", "pending")]
    m = _Mig("running", {"min_free_bytes": 50, "window": WINDOW})
    m.pause_reason = None
    m.last_occurrence = "2026-07-01"
    m.logs = []
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (20, 100)
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "space"
    entry = [e for e in m.logs if e["event"] == "paused_min_free"][-1]
    assert entry["min_free_bytes"] == 50


def test_space_pause_resumes_when_the_floor_clears(monkeypatch):
    items = [_item("r", "pending")]
    m = _space_paused({"min_free_pct": 10})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (80, 100)
    result = r.tick()
    assert m.status == MigrationStatus.RUNNING.value
    assert m.pause_reason is None
    assert any(e["event"] == "resumed_min_free" for e in m.logs)
    assert ("r", None, "deferred") not in result


def test_space_pause_stays_while_still_below_the_floor(monkeypatch):
    items = [_item("r", "pending")]
    m = _space_paused({"min_free_bytes": 50})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: (20, 100)
    result = r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "space"
    assert items[0]["state"] == "pending"
    assert result == [("r", None, "deferred")]


def test_space_pause_does_not_resume_on_an_unknown_reading(monkeypatch):
    items = [_item("r", "pending")]
    m = _space_paused({"min_free_pct": 10})
    r = _runner(monkeypatch, items, m, now=NOW)
    r.free_space_fn = lambda: None
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert items[0]["state"] == "pending"


def test_space_pause_is_not_rechecked_outside_the_window(monkeypatch):
    items = [_item("r", "pending")]
    m = _space_paused({"min_free_pct": 10})

    def _boom():
        raise AssertionError("no probe outside the window")

    r = _runner(monkeypatch, items, m, now=datetime(2026, 7, 1, 20, 0))
    r.free_space_fn = _boom
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "space"
    assert items[0]["state"] == "pending"


def test_space_pause_still_drives_trees_in_flight(monkeypatch):
    items = [
        _item("a", "moving", tree="a", move_task_id="mt"),
        _item("b", "pending", tree="b"),
    ]
    m = _space_paused({"min_free_bytes": 50})
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "finished")
    r.free_space_fn = lambda: (20, 100)
    r.tick()
    assert items[0]["state"] != "moving"
    assert items[1]["state"] == "pending"
    assert m.status == MigrationStatus.PAUSED.value


def test_a_failure_during_a_space_pause_becomes_a_failure_pause(monkeypatch):
    items = [
        _item("a", "moving", tree="a", move_task_id="mt"),
        _item("b", "pending", tree="b"),
    ]
    m = _space_paused({"min_free_bytes": 50, "failure_policy": "pause"})
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "failed")
    r.free_space_fn = lambda: (20, 100)
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "failure"


def test_recurring_job_paused_for_space_resumes_next_night(monkeypatch):
    items = [_item("r", "released"), _item("n", "pending", tree="n")]
    planned = [_item("n", "pending", tree="n")]
    m = _space_paused(
        {"recurring": True, "rescan_cadence": "edge", "min_free_bytes": 50}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.free_space_fn = lambda: (80, 100)
    result = r.tick()
    assert m.status == MigrationStatus.RUNNING.value
    assert m.last_occurrence == "2026-07-01"
    assert ("n", None, "deferred") not in result


def test_recurring_job_still_short_of_space_next_night_stays_paused(monkeypatch):
    items = [_item("r", "released"), _item("n", "pending", tree="n")]
    planned = [_item("n", "pending", tree="n")]
    m = _space_paused(
        {"recurring": True, "rescan_cadence": "edge", "min_free_bytes": 50}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.free_space_fn = lambda: (20, 100)
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.last_occurrence == "2026-06-30"
    assert items[1]["state"] == "pending"


def test_space_pause_completes_when_its_last_tree_lands(monkeypatch):
    items = [_item("r", "released")]
    m = _space_paused({"min_free_bytes": 50})
    r = _runner(monkeypatch, items, m, now=datetime(2026, 7, 1, 20, 0))
    r.tick()
    assert m.status == MigrationStatus.COMPLETED.value
    assert m.pause_reason is None


def test_load_policy_leaves_a_space_pause_to_the_tick(monkeypatch):
    items = [_item("r", "pending")]
    m = _space_paused({"min_free_pct": 10})
    r = _runner(monkeypatch, items, m, now=NOW)
    assert r._apply_load_policy() is False
    m.pause_reason = "manual"
    assert r._apply_load_policy() is True


class _Lock:
    def acquire(self):
        return False


class _Conn:
    def lock(self, *a, **k):
        return _Lock()


@pytest.mark.parametrize(
    "reason, outcome",
    [
        ("space", "busy"),
        ("load", "busy"),
        ("manual", "not_drivable"),
        ("failure", "not_drivable"),
    ],
)
def test_advance_drives_only_self_resuming_pauses(monkeypatch, reason, outcome):
    job = type("M", (), {"status": "paused", "pause_reason": reason})()

    class _SM:
        exists = staticmethod(lambda mid: True)

        def __new__(cls, mid):
            return job

    monkeypatch.setattr(mr, "StorageMigration", _SM)
    monkeypatch.setattr(mr.redis, "from_url", lambda *a, **k: _Conn())
    assert mr.advance("m") == outcome


def test_describe_space_floor_names_both_floors():
    gib = 1024**3
    text = mig.describe_space_floor(5 * gib, 100 * gib, 10, 20 * gib)
    assert text == "5 GiB (5.0%) free of 100 GiB; floor 10% and 20 GiB"
