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
