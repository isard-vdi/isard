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
    """``status`` is what the driver read; ``live`` is the row the guarded write
    tests. They diverge when the admin writes it mid-tick."""

    def __init__(self, status, config, selection=None, live_status=None):
        self.id = "m"
        self.live = {"status": live_status if live_status is not None else status}
        object.__setattr__(self, "status", status)
        self.config = config
        self.selection = selection or {"kind": "pool", "dst_pool_id": "dst"}
        self.current_window = None
        self.last_occurrence = None
        self.throughput_ewma = {}
        self.pause_reason = None

    def __setattr__(self, name, value):
        # an unguarded write must show on the live row, or nothing is proven;
        # pause_reason is a real column too (the resume claim keys on it).
        if name in ("status", "pause_reason") and "live" in self.__dict__:
            self.live[name] = value
        object.__setattr__(self, name, value)

    def _update_cache(self, **fields):
        pass

    def fresh_status(self):
        for name in ("status", "pause_reason"):
            if name in self.live:
                object.__setattr__(self, name, self.live[name])
        return self.status, self.pause_reason

    def fresh_config(self):
        return self.config

    def update_document(self, _doc_id, update_data, *, validate=True):
        # model rethinkdb's nested deep-merge for a partial config write
        for key, value in update_data.items():
            if isinstance(value, dict) and isinstance(getattr(self, key, None), dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)

    def recompute_totals(self, items=None):
        pass


def _patch_status_claim(monkeypatch, mig_obj):
    """Honour ``update_document_if`` against the live row of ``mig_obj``."""

    def _claim(
        cls, doc_id, update_data, *, field, values=None, excluding=None, validate=True
    ):
        held = mig_obj.live.get(field)
        if (values is not None and held not in values) or (
            excluding is not None and held in excluding
        ):
            return False
        mig_obj.live.update(update_data)
        for key, value in update_data.items():
            object.__setattr__(mig_obj, key, value)
        return True

    monkeypatch.setattr(mr.StorageMigration, "update_document_if", classmethod(_claim))


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

        @staticmethod
        def exists(sid):
            return True

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _Storage)
    _patch_status_claim(monkeypatch, mig_obj)

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = mig_obj
    r.config = mig_obj.config
    r.user_id = "admin"
    r.dst_pool = None
    r.job_status_fn = job_status_fn
    r._now = lambda tz: now
    r._domains = lambda sid: []
    r._publish_progress = lambda *a, **k: None
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
    # a manual pause is not parked by the loop either: the tick holds it, so the
    # trees already moving still finish
    m.pause_reason = "manual"
    assert r._apply_load_policy() is False


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
    # nothing moving: a manual/failure pause has nothing left to finish
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "state_counts",
        classmethod(lambda cls, mid: {"pending": 2}),
    )
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: _Conn())
    assert mr.advance("m") == outcome


def test_describe_space_floor_names_both_floors():
    gib = 1024**3
    text = mig.describe_space_floor(5 * gib, 100 * gib, 10, 20 * gib)
    assert text == "5 GiB (5.0%) free of 100 GiB; floor 10% and 20 GiB"


# --------------------------------------------------------------------------- #
# a disk that came back to the source moves again on the next occurrence
# --------------------------------------------------------------------------- #
def _returned_job():
    m = _Mig(
        "scheduled",
        {"recurring": True, "window": WINDOW, "rescan_cadence": "edge_on_drain"},
    )
    m.last_occurrence = "2026-06-30"
    return m


def _released(sid="r"):
    return _item(
        sid,
        "released",
        src_path=f"/src/old/{sid}.qcow2",
        verify_passed=True,
        source_action="delete",
        move_task_id="old",
        audit=[{"occurrence": "2026-06-30", "result": "moved_ok"}],
    )


def test_a_released_disk_back_on_the_source_moves_again(monkeypatch):
    items = [_released()]
    planned = [_item("r", "pending", src_path="/src/new/r.qcow2")]
    m = _returned_job()
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    it = items[0]
    assert m.last_occurrence == "2026-07-01"
    assert it["state"] != "released"
    assert it["src_path"] == "/src/new/r.qcow2"
    assert it["verify_passed"] is False
    assert it["source_action"] is None
    assert it["move_task_id"] != "old"
    assert it["audit"] == [{"occurrence": "2026-06-30", "result": "moved_ok"}]


def test_a_returned_disk_of_an_ordered_job_moves_again(monkeypatch):
    items = [_released()]
    planned = [_item("r", "pending", tree_order_key=1790446574.4959528)]
    m = _returned_job()
    m.config["order"] = "oldest_first"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert items[0]["state"] != "released"
    assert items[0]["tree_order_key"] == 1790446574.4959528


def test_a_released_disk_not_back_on_the_source_stays_released(monkeypatch):
    items = [_released()]
    m = _returned_job()
    r = _runner(monkeypatch, items, m, now=NOW, planned=[])
    r.tick()
    assert items[0]["state"] == "released"
    assert items[0]["source_action"] == "delete"


def test_a_disk_moves_at_most_once_per_occurrence(monkeypatch):
    items = [_released()]
    planned = [_item("r", "pending", src_path="/src/new/r.qcow2")]
    m = _returned_job()
    m.last_occurrence = "2026-07-01"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert items[0]["state"] == "released"


def test_an_admin_cancel_landing_mid_tick_is_not_overwritten(monkeypatch):
    """The advance lease excludes other drivers, not apiv4's unlocked set_action."""
    items = [_item("r", "released")]
    m = _Mig("running", {"recurring": True, "window": WINDOW})
    r = _runner(monkeypatch, items, m, now=NOW)
    real_items = r._items

    def _items_then_admin_cancels():
        # after the tick read the status, before it writes one
        m.live["status"] = MigrationStatus.FINISHING_TREE.value
        return real_items()

    r._items = _items_then_admin_cancels

    r.tick()

    assert m.live["status"] == MigrationStatus.FINISHING_TREE.value


# --- an admin pause finishes what is moving and starts nothing new ---
@pytest.mark.parametrize("reason", ["manual", "failure"])
def test_a_paused_job_finishes_the_trees_in_flight_and_starts_none(monkeypatch, reason):
    # tree "a" is mid-move (its copy just finished); tree "b" has not started
    items = [
        _item("a", "moving", tree="a", move_task_id="mt"),
        _item("b", "pending", tree="b"),
    ]
    m = _Mig("paused", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"})
    m.pause_reason = reason
    m.last_occurrence = "2026-07-01"
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "finished")
    results = r.tick()
    assert items[0]["state"] != "moving"  # the in-flight disk advanced
    assert items[1]["state"] == "pending"  # nothing new admitted
    assert ("b", None, "deferred") in results
    assert m.status == MigrationStatus.PAUSED.value  # still waiting for the admin
    assert m.pause_reason == reason


def test_a_paused_job_is_not_rescanned(monkeypatch):
    items = [_item("a", "moving", tree="a", move_task_id="mt")]
    planned = [_item("a", "moving", tree="a"), _item("n", "pending", tree="n")]
    m = _Mig("paused", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"})
    m.pause_reason = "manual"
    m.last_occurrence = "2026-06-30"  # an edge: would re-scan if not held
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert [it["storage_id"] for it in items] == ["a"]  # no new disk inserted
    assert m.last_occurrence == "2026-06-30"


def test_a_held_pause_is_not_turned_into_a_space_pause(monkeypatch):
    """A space breach while an admin holds the job must not make it self-resuming."""
    items = [_item("a", "moving", tree="a", move_task_id="mt")]
    m = _Mig("paused", {"recurring": True, "window": WINDOW, "min_free_pct": 10})
    m.pause_reason = "manual"
    m.last_occurrence = "2026-07-01"
    r = _runner(monkeypatch, items, m, now=NOW)
    r._space_floor_breached = lambda: True
    r.tick()
    assert m.status == MigrationStatus.PAUSED.value
    assert m.pause_reason == "manual"


def test_the_tick_reads_the_status_afresh(monkeypatch):
    # the runner is reused for a whole drain: a pause written between two ticks
    # must be honoured by the next one, not by the next drain
    items = [_item("b", "pending", tree="b")]
    m = _Mig("running", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"})
    m.last_occurrence = "2026-07-01"
    r = _runner(monkeypatch, items, m, now=NOW)
    m.live.update(status=MigrationStatus.PAUSED.value, pause_reason="manual")
    results = r.tick()
    assert items[0]["state"] == "pending"
    assert ("b", None, "deferred") in results


# --- a tree that no longer matches the selection is not moved ---
def test_an_unstarted_tree_that_left_the_selection_is_skipped(monkeypatch):
    # planned when cold; used since, so the re-plan at the window edge drops it
    items = [_item("hot", "pending", tree="hot"), _item("cold", "pending", tree="cold")]
    planned = [_item("cold", "pending", tree="cold")]
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    hot = next(it for it in items if it["storage_id"] == "hot")
    assert hot["state"] == "skipped"
    assert hot["error"] == "no longer matches the selection"
    cold = next(it for it in items if it["storage_id"] == "cold")
    assert cold["state"] != "skipped"


def test_a_tree_in_flight_is_never_skipped_by_a_replan(monkeypatch):
    items = [_item("a", "moving", tree="a", move_task_id="mt")]
    m = _Mig("running", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"})
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=[])
    r.tick()
    assert items[0]["state"] != "skipped"


def test_a_busy_disk_absent_from_the_replan_waits_instead(monkeypatch):
    # the selection only offers ready disks: one busy with another task is not
    # out of the selection, it keeps its place
    items = [_item("busy", "pending", tree="busy")]
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=[])

    class _Busy:
        def __init__(self, sid):
            self.status = "maintenance"

        @staticmethod
        def exists(sid):
            return True

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _Busy)
    r._admit_tree = lambda *a, **k: False  # only the re-plan acts this tick
    r.tick()
    assert items[0]["state"] == "pending"


def test_a_skipped_stale_tree_comes_back_when_it_matches_again(monkeypatch):
    items = [_item("t", "skipped", tree="t", error="no longer matches the selection")]
    planned = [_item("t", "pending", tree="t")]
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(monkeypatch, items, m, now=NOW, planned=planned)
    r.tick()
    assert items[0]["state"] != "skipped"
    assert items[0]["occurrence_failures"] == 0  # a skip is not a failure


# --- F1: an admin action that lands during a space_deferred tick survives ----- #
def _running_job():
    m = _Mig("running", {"window": WINDOW})
    m.last_occurrence = "2026-07-01"
    m.logs = []
    m.space_probe = {}
    return m


_SPACE_REFUSAL = "move: refusing to copy /x: destination below the 1 byte floor"


def test_admin_cancel_during_a_space_deferred_tick_is_not_clobbered(monkeypatch):
    """The worker refuses a move for lack of room mid-tick (-> space_deferred). If
    an admin cancel lands in that same tick, the end-of-tick space pause must not
    overwrite the finishing_tree the cancel wrote (a status-keyed claim loses the
    race; the old unconditional write clobbered it, and _claim_resume would then
    auto-resume the space pause -- the cancel vanishes)."""
    items = [_item("a", "moving", tree="a", move_task_id="mt")]
    m = _running_job()
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "failed")

    def _reason_then_admin_cancels(item):
        m.live["status"] = "finishing_tree"  # admin cancel lands concurrently
        return _SPACE_REFUSAL

    r._failure_reason = _reason_then_admin_cancels
    r.tick()

    assert items[0]["state"] == "pending"  # the disk was deferred, not failed
    assert (
        m.live["status"] == "finishing_tree"
    ), "admin cancel clobbered to paused/space"
    assert m.live.get("pause_reason") != "space"


def test_admin_pause_during_a_space_deferred_tick_is_not_clobbered(monkeypatch):
    items = [_item("a", "moving", tree="a", move_task_id="mt")]
    m = _running_job()
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "failed")

    def _reason_then_admin_pauses(item):
        m.live["status"] = "paused"
        m.live["pause_reason"] = "manual"  # admin manual pause lands concurrently
        return _SPACE_REFUSAL

    r._failure_reason = _reason_then_admin_pauses
    r.tick()

    assert items[0]["state"] == "pending"
    assert m.live["status"] == "paused"
    assert m.live["pause_reason"] == "manual", "manual pause overwritten to space"


# --- F3: cancelling a parked job drains through finishing_tree ---------------- #
WINDOW_CLOSED = {"start": "20:00", "end": "22:00", "days": [], "tz": "UTC"}


@pytest.mark.parametrize("recurring", [False, True])  # budget_reached | scheduled
def test_cancel_of_a_parked_job_drains_and_reactivates_once(monkeypatch, recurring):
    """cancel_target sends budget_reached/scheduled to finishing_tree; driving that
    with the window CLOSED and only pending disks must skip them without starting,
    reach canceled, and restore autostart exactly once (reactivate is the other
    session's code -- called here, never modified)."""
    items = [_item("a", "pending", tree="a")]
    cfg = {"window": WINDOW_CLOSED}
    if recurring:
        cfg["recurring"] = True
    m = _Mig("finishing_tree", cfg)
    m.last_occurrence = "2026-07-01"
    m.logs = []
    r = _runner(monkeypatch, items, m, now=NOW)
    calls = {"n": 0}
    r.reactivate = lambda: calls.__setitem__("n", calls["n"] + 1)
    r.tick()
    assert items[0]["state"] == "skipped"  # pending tree canceled, never started
    assert m.live["status"] == "canceled"
    assert calls["n"] == 1  # autostart restored exactly once


def test_cancel_one_parked_migration_does_not_touch_another(monkeypatch):
    """Driving A's cancel to completion never reads or writes B's row or items:
    every ledger read is scoped by migration_id and every status claim keys on A's
    id. B keeps its status and its disk mid-move."""
    a_items = [_item("a", "pending", tree="a")]
    a_items[0].update(id="A--a", migration_id="A")
    b_items = [_item("b", "moving", tree="b", move_task_id="mt")]
    b_items[0].update(id="B--b", migration_id="B")
    all_items = a_items + b_items

    a = _Mig("finishing_tree", {"window": WINDOW})
    a.id = "A"
    a.last_occurrence = "2026-07-01"
    a.logs = []
    b = _Mig("running", {"window": WINDOW})
    b.id = "B"
    migs = {"A": a, "B": b}

    def _claim(cls, doc_id, update_data, *, field, values=None, excluding=None, **_k):
        mo = migs[doc_id]
        held = mo.live.get(field)
        if (values is not None and held not in values) or (
            excluding is not None and held in excluding
        ):
            return False
        mo.live.update(update_data)
        for key, value in update_data.items():
            object.__setattr__(mo, key, value)
        return True

    monkeypatch.setattr(mr.StorageMigration, "update_document_if", classmethod(_claim))
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(
            lambda cls, mid: [it for it in all_items if it["migration_id"] == mid]
        ),
    )

    def _update(cls, iid, fields, validate=True):
        for it in all_items:
            if it["id"] == iid:
                it.update(fields)

    monkeypatch.setattr(
        mr.StorageMigrationItem, "update_document", classmethod(_update)
    )
    monkeypatch.setattr(mig, "roots_for_selection", lambda sel: ["a"])
    monkeypatch.setattr(
        mig, "build_plan_for_roots", lambda mid, roots, pool, **k: ([], {})
    )

    class _Storage:
        def __init__(self, sid):
            self.status = "ready"

        @staticmethod
        def exists(sid):
            return True

        @classmethod
        def update_document(cls, sid, fields, validate=True):
            pass

    monkeypatch.setattr(mr, "Storage", _Storage)

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "A"
    r.migration = a
    r.config = a.config
    r.user_id = "admin"
    r.dst_pool = None
    r.job_status_fn = lambda t: None
    r._now = lambda tz: NOW
    r._domains = lambda sid: []
    r._publish_progress = lambda *a, **k: None
    r.prepare = lambda: None
    r.reactivate = lambda: None
    r._enqueue = lambda *a, **k: "tid"
    r._pool_queue = lambda p, action: "q"
    r._move_queue = lambda p: "q"
    r._pool_of = lambda p: type("P", (), {"id": "p"})()
    r._admit_tree = lambda *a, **k: True
    r._restore_storage_status = lambda it: None
    r.tick()

    assert a.live["status"] == "canceled"
    assert a_items[0]["state"] == "skipped"
    assert b.live["status"] == "running"  # B untouched
    assert b_items[0]["state"] == "moving"  # B's disk still mid-move
