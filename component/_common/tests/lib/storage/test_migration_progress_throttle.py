# SPDX-License-Identifier: AGPL-3.0-or-later

"""Producer-side progress throttle (Phase 2).

``_publish_progress`` XADDs a ``kind=migration`` event so the change-handler
refreshes the admin socket. A long drain used to XADD on every tick/drain, so a
nightly job of thousands of disks flooded the shared result stream (and the
reads its consumers do). It is now throttled to one event per migration per
``PROGRESS_THROTTLE_S`` via a Redis NX key, EXCEPT when forced — a status change
this tick, or any pause/park — which the admin must see at once. Best-effort
throughout: a Redis hiccup never fails the tick.
"""

from datetime import datetime

import isardvdi_common.lib.storage.migration_run as mr
import pytest
from isardvdi_common.models.storage_migration import MigrationStatus


class _Conn:
    """A fake redis: ``set`` models the NX throttle key, ``xadd`` records events.
    ``fail`` makes the named call raise, to prove best-effort never propagates."""

    def __init__(self, set_result=True, fail=None):
        self.set_result = set_result
        self.fail = fail
        self.sets = []
        self.xadds = []

    def set(self, key, value, nx=False, ex=None):
        if self.fail == "set":
            raise RuntimeError("redis down")
        self.sets.append({"key": key, "nx": nx, "ex": ex})
        return self.set_result

    def xadd(self, stream, fields, maxlen=None, approximate=None):
        if self.fail == "xadd":
            raise RuntimeError("redis down")
        self.xadds.append(fields)
        return b"1-0"


def _runner(monkeypatch, conn):
    monkeypatch.setattr(mr, "shared_client", lambda url: conn)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")
    monkeypatch.setattr(mr.task_streams, "maxlen_for_stream", lambda s: 1000)
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    return r


def test_the_first_publish_takes_the_key_and_xadds(monkeypatch):
    conn = _Conn(set_result=True)  # key was free
    _runner(monkeypatch, conn)._publish_progress()
    assert len(conn.xadds) == 1
    assert conn.sets[0]["key"] == "migration:progress:m1"
    assert conn.sets[0]["nx"] is True
    assert conn.sets[0]["ex"] == mr.PROGRESS_THROTTLE_S


def test_a_throttled_publish_is_skipped(monkeypatch):
    conn = _Conn(set_result=None)  # key already present -> within the window
    _runner(monkeypatch, conn)._publish_progress()
    assert conn.xadds == []


def test_force_bypasses_the_throttle_without_consulting_the_key(monkeypatch):
    conn = _Conn(set_result=None)  # would be throttled
    _runner(monkeypatch, conn)._publish_progress(force=True)
    assert len(conn.xadds) == 1
    assert conn.sets == []  # a forced event never touches the throttle key


@pytest.mark.parametrize("fail", ["set", "xadd"])
def test_a_redis_failure_never_raises(monkeypatch, fail):
    conn = _Conn(fail=fail)
    _runner(monkeypatch, conn)._publish_progress()  # must not raise


# --------------------------------------------------------------------------- #
# tick wiring: a status change forces past the throttle; a quiet tick does not
# --------------------------------------------------------------------------- #
_OPEN = {"start": "09:00", "end": "17:00", "days": [], "tz": "UTC"}
NOW = datetime(2026, 7, 1, 12, 0)


class _TMig:
    def __init__(self, status, config):
        self.id = "m"
        self.live = {"status": status}
        object.__setattr__(self, "status", status)
        self.config = config
        self.selection = {"kind": "pool", "dst_pool_id": "dst"}
        self.current_window = None
        self.last_occurrence = None
        self.throughput_ewma = {}
        self.pause_reason = None


    def __setattr__(self, name, value):
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
        for key, value in update_data.items():
            if isinstance(value, dict) and isinstance(getattr(self, key, None), dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)

    def recompute_totals(self, items=None):
        pass


def _item(sid, state, tree="r"):
    return {
        "id": f"m--{sid}",
        "migration_id": "m",
        "storage_id": sid,
        "tree_id": tree,
        "topo_index": 0,
        "state": state,
        "size_bytes": 10,
        "src_path": f"/src/{sid}.qcow2",
        "dst_path": f"/dst/{sid}.qcow2",
        "occurrence_failures": 0,
        "audit": [],
        "parent_dst_path": None,
    }


def _tick_runner(monkeypatch, items, mig_obj):
    import isardvdi_common.lib.storage.migration as mig

    monkeypatch.setattr(
        mr.StorageMigrationItem, "dicts_by_migration", classmethod(lambda cls, m: items)
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(lambda cls, iid, fields, validate=True: None),
    )

    def _status_claim(
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

    monkeypatch.setattr(
        mr.StorageMigration, "update_document_if", classmethod(_status_claim)
    )
    monkeypatch.setattr(mig, "roots_for_selection", lambda sel: [])
    monkeypatch.setattr(
        mig, "build_plan_for_roots", lambda mid, roots, pool, **k: ([], {})
    )

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = mig_obj
    r.config = mig_obj.config
    r.user_id = "admin"
    r.dst_pool = None
    r.job_status_fn = lambda t: "started"
    r._now = lambda tz: NOW
    r._domains = lambda sid: []
    r.prepare = lambda: None
    r.reactivate = lambda: None
    r._gate_tree = lambda tree_items: True
    r._admit_tree = lambda *a, **k: True
    forces = []
    r._publish_progress = lambda force=False: forces.append(force)
    return r, forces


def test_the_end_of_tick_publish_forces_on_a_status_change(monkeypatch):
    # a recurring job that drained transitions running -> scheduled this tick
    items = [_item("r", "released")]
    m = _TMig("running", {"recurring": True, "window": _OPEN, "rescan_cadence": "edge"})
    m.last_occurrence = "2026-07-01"
    r, forces = _tick_runner(monkeypatch, items, m)
    r.tick()
    assert m.status == MigrationStatus.SCHEDULED.value
    assert forces[-1] is True  # the transition forced past the throttle


def test_the_end_of_tick_publish_does_not_force_on_a_quiet_tick(monkeypatch):
    # an in-flight disk, no transition: the publish is throttle-eligible
    items = [_item("a", "moving")]
    items[0]["move_task_id"] = "mt"
    m = _TMig("running", {"window": _OPEN})
    m.last_occurrence = "2026-07-01"
    r, forces = _tick_runner(monkeypatch, items, m)
    r.tick()
    assert m.status == MigrationStatus.RUNNING.value
    assert forces[-1] is False  # no status change -> may be throttled
