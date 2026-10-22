# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-event driving: a task result moves only its own tree, a settled tree frees
its slot for the next one of the frozen order, and the whole ledger is read only
by the full pass."""

import pytest
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import totals_delta

from .test_migration_recurring_drive import NOW, _FakeRedis, _item, _Mig, _runner

ORDER = "migration:order:m"


def _scripted_saga(monkeypatch, finished):
    """A two-step saga per disk: ``start`` enqueues, ``finish`` releases once
    the disk's task is in ``finished``. Keeps these tests about scheduling."""

    def tree_next(tree_items, job_status_fn):
        for it in sorted(tree_items, key=lambda i: i["topo_index"]):
            if it["state"] == "pending":
                return it, "start"
            if it["state"] == "moving":
                if job_status_fn(it["move_task_id"]) == "finished":
                    return it, "finish"
                return it, "wait"
        return None, "noop"

    monkeypatch.setattr(mig, "tree_next", tree_next)
    monkeypatch.setattr(mig, "PROGRESS_ACTIONS", {"start", "finish"})
    return lambda tid: "finished" if tid in finished else "started"


def _event_runner(monkeypatch, items, *, active, order, parallelism=1, config=None):
    m = _Mig("running", {"parallelism": parallelism, **(config or {})})
    m.drive = {"active": list(active), "window_open": True, "drained": False}
    deltas = []
    m.record_activity = lambda delta=None: deltas.append(delta)
    finished = set()
    r = _runner(
        monkeypatch,
        items,
        m,
        now=NOW,
        job_status_fn=_scripted_saga(monkeypatch, finished),
    )
    redis = _FakeRedis()
    redis.rpush(ORDER, *order)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")

    def _start(self, item):
        self._set(item, state="moving", move_task_id=f"t-{item['storage_id']}")

    def _finish(self, item):
        self._set(item, state="released")

    r._ACTIONS = {"start": _start, "finish": _finish}
    tree_reads = []

    def _tree_rows(cls, mid, tree_id):
        tree_reads.append(tree_id)
        return [it for it in items if it["tree_id"] == tree_id]

    monkeypatch.setattr(mr.StorageMigrationItem, "tree_rows", classmethod(_tree_rows))

    def _no_full_read(cls, mid):
        raise AssertionError("a per-event drive read the whole ledger")

    monkeypatch.setattr(
        mr.StorageMigrationItem, "dicts_by_migration", classmethod(_no_full_read)
    )
    prepared, restored = [], []
    r.prepare = lambda tree_items=None: prepared.append(
        [it["storage_id"] for it in tree_items]
    )
    r.reactivate = lambda tree_items=None: restored.append(
        [it["storage_id"] for it in tree_items]
    )
    return r, m, redis, finished, tree_reads, prepared, restored, deltas


def _three_trees():
    return [
        _item("a", "moving", tree="a", move_task_id="t-a"),
        _item("b", "pending", tree="b"),
        _item("c", "pending", tree="c"),
    ]


def test_a_result_drives_its_tree_and_admits_the_next_one_in_order(monkeypatch):
    items = _three_trees()
    r, m, redis, finished, tree_reads, prepared, restored, deltas = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"]
    )
    finished.add("t-a")

    r.drive_trees(["a"])

    assert [it["state"] for it in items] == ["released", "moving", "pending"]
    assert tree_reads == ["a", "b"]
    assert m.drive["active"] == ["b"]
    assert redis.lists[ORDER] == ["c"]
    # autostart is held off from the admitted tree and given back to the settled one
    assert prepared == [["b"]]
    assert restored == [["a"]]
    # the totals follow each disk by delta, not by a recount
    assert [d["state_counts"] for d in deltas] == [
        {"moving": -1, "released": 1},
        {"pending": -1, "moving": 1},
    ]


def test_a_result_of_a_tree_not_in_flight_is_ignored(monkeypatch):
    items = _three_trees()
    r, m, redis, finished, tree_reads, *_ = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"]
    )

    r.drive_trees(["z"])

    # nothing read but the admission check, which finds no free slot
    assert tree_reads == []
    assert m.drive["active"] == ["a"]


def test_a_still_running_task_admits_nothing(monkeypatch):
    items = _three_trees()
    r, m, redis, finished, tree_reads, *_ = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"]
    )

    r.drive_trees(["a"])

    assert items[0]["state"] == "moving"
    assert redis.lists[ORDER] == ["b", "c"]


def test_freed_slots_fill_up_to_the_parallelism(monkeypatch):
    items = _three_trees()
    r, m, redis, finished, *_ = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"], parallelism=3
    )

    r.drive_trees(None)

    assert m.drive["active"] == ["a", "b", "c"]
    assert ORDER not in redis.lists or redis.lists[ORDER] == []


@pytest.mark.parametrize("status", ["paused", "finishing_tree"])
def test_a_held_or_canceling_job_admits_nothing(monkeypatch, status):
    items = _three_trees()
    r, m, redis, finished, *_ = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"]
    )
    object.__setattr__(m, "status", status)
    m.pause_reason = "manual" if status == "paused" else None
    finished.add("t-a")

    r.drive_trees(["a"])

    assert items[0]["state"] == "released"
    assert redis.lists[ORDER] == ["b", "c"]


def test_the_budget_stops_admission(monkeypatch):
    items = _three_trees()
    r, m, redis, finished, *_ = _event_runner(
        monkeypatch,
        items,
        active=["a"],
        order=["b", "c"],
        config={"max_bytes_per_occurrence": 10},
    )
    m.budget_spent = {"occurrence": "initial", "bytes": 10}
    finished.add("t-a")

    r.drive_trees(["a"])

    assert redis.lists[ORDER] == ["b", "c"]
    assert m.status == "budget_reached"


def test_a_tree_that_does_not_fit_the_window_is_dropped_until_it_reopens(
    monkeypatch,
):
    items = _three_trees()
    r, m, redis, finished, *_ = _event_runner(
        monkeypatch, items, active=["a"], order=["b", "c"]
    )
    r._admit_tree = lambda tree_items, *a: tree_items[0]["tree_id"] != "b"
    finished.add("t-a")

    r.drive_trees(["a"])

    assert items[1]["state"] == "pending"
    assert items[2]["state"] == "moving"
    assert m.drive["active"] == ["c"]


# -- when a full pass is due
def _pass_runner(monkeypatch, drive, *, status="running", order=()):
    m = _Mig(status, {})
    m.drive = drive
    r = _runner(monkeypatch, [], m, now=NOW)
    redis = _FakeRedis()
    if order:
        redis.rpush(ORDER, *order)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")
    return r


@pytest.mark.parametrize(
    "drive, status, order, full",
    [
        (None, "running", (), True),
        ({"active": ["a"], "window_open": True}, "running", (), False),
        ({"active": [], "window_open": True}, "running", ("b",), False),
        # nothing in flight or waiting: the full pass decides the job's end
        ({"active": [], "window_open": True}, "running", (), True),
        ({"active": [], "window_open": True, "drained": True}, "running", (), False),
        # the window just opened
        ({"active": ["a"], "window_open": False}, "running", (), True),
        # a cancel skips every tree not yet started, once
        ({"active": ["a"], "window_open": True}, "finishing_tree", (), True),
        (
            {"active": ["a"], "window_open": True, "finishing": True},
            "finishing_tree",
            (),
            False,
        ),
    ],
)
def test_needs_full_pass(monkeypatch, drive, status, order, full):
    r = _pass_runner(monkeypatch, drive, status=status, order=order)
    assert r.needs_full_pass() is full


def test_save_drive_freezes_the_order_and_the_trees_in_flight(monkeypatch):
    items = [
        _item("a", "moving", tree="a", tree_order_key=1),
        _item("b", "pending", tree="b", tree_order_key=30),
        _item("c", "pending", tree="c", tree_order_key=20),
        _item("d", "released", tree="d", tree_order_key=10),
        # waiting for its desktop to stop: it already holds a slot
        _item("e", "pending", tree="e", tree_order_key=5, attempts=2),
    ]
    m = _Mig("running", {"order": "oldest_first"})
    r = _runner(monkeypatch, items, m, now=NOW)
    redis = _FakeRedis()
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")

    r.save_drive()

    assert m.drive["active"] == ["a", "e"]
    assert redis.lists[ORDER] == ["c", "b"]
    assert m.drive["drained"] is False
    assert m.drive["window_open"] is True


def test_save_drive_of_a_finished_job_is_drained(monkeypatch):
    m = _Mig("completed", {})
    r = _runner(monkeypatch, [_item("a", "released", tree="a")], m, now=NOW)
    redis = _FakeRedis()
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")

    r.save_drive()

    assert m.drive["drained"] is True and m.drive["active"] == []


# -- advance(): one full pass, then per-tree drives; no wake lost to "busy"
class _Lock:
    def __init__(self, free):
        self.free = free

    def acquire(self):
        return self.free

    def reacquire(self):
        return True

    def release(self):
        pass


def _advance_env(monkeypatch, *, free, full=False):
    class _SM:
        exists = staticmethod(lambda mid: True)

        def __init__(self, mid):
            self.status = "running"
            self.pause_reason = None

    monkeypatch.setattr(mr, "StorageMigration", _SM)
    redis = _FakeRedis()
    redis.lock = lambda *a, **k: _Lock(free)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    calls = []

    class _Runner:
        def __init__(self, mid, *, job_status_fn):
            self.full = full

        def needs_full_pass(self):
            return self.full

        def tick(self):
            calls.append("tick")
            return []

        def is_complete(self):
            return False

        def save_drive(self):
            calls.append("save_drive")
            self.full = False

        def drive_trees(self, tree_ids):
            calls.append(("drive", tree_ids))

    monkeypatch.setattr(mr, "MigrationRunner", _Runner)
    return redis, calls


def test_a_busy_wake_is_kept_for_the_holder(monkeypatch):
    redis, calls = _advance_env(monkeypatch, free=False)

    assert mr.advance("m", tree_ids=["t1"]) == "busy"
    assert redis.sets["migration:wake:m"] == {"t1"}
    assert calls == []


def test_the_holder_drives_every_tree_woken_while_it_held_the_lease(monkeypatch):
    redis, calls = _advance_env(monkeypatch, free=True)
    redis.sadd("migration:wake:m", "t1")

    assert mr.advance("m", tree_ids=["t2"]) == "done"
    assert calls == [("drive", ["t1", "t2"])]
    assert not redis.exists("migration:wake:m")


def test_the_periodic_drive_covers_every_tree_in_flight(monkeypatch):
    redis, calls = _advance_env(monkeypatch, free=True)

    mr.advance("m")

    assert calls == [("drive", None)]


def test_a_full_pass_runs_once_and_consumes_the_wakes(monkeypatch):
    redis, calls = _advance_env(monkeypatch, free=True, full=True)

    mr.advance("m", tree_ids=["t1"])

    assert calls == ["tick", "save_drive"]


# -- totals by delta, and the autostart hand-over between migrations
def test_totals_delta_follows_a_disk_through_the_saga():
    assert totals_delta("pending", "moving", 5) == {
        "state_counts": {"pending": -1, "moving": 1}
    }
    assert totals_delta("rebased", "released", 5) == {
        "state_counts": {"rebased": -1, "released": 1},
        "done": 1,
        "completed": 1,
        "bytes_done": 5,
    }
    assert totals_delta("moving", "moved", 5) == {
        "state_counts": {"moving": -1, "moved": 1},
        "migrated": 1,
        "bytes_copied": 5,
    }


def test_a_desktop_still_moving_elsewhere_is_handed_over_not_restored(monkeypatch):
    other = {
        "id": "m2--s9",
        "state": "moving",
        "autostart_domains": [{"id": "d1", "was_on": False}],
    }
    written = []

    class _Dom:
        def __init__(self, did):
            self.create_dict = {"hardware": {"disks": [{"storage_id": "s9"}]}}

    monkeypatch.setattr(mr, "Domain", _Dom)
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_storage",
        classmethod(lambda cls, sid: [other]),
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(lambda cls, iid, f, validate=True: written.append((iid, f))),
    )
    activated = []
    monkeypatch.setattr(
        mr.DesktopEvents,
        "activate_autostart",
        staticmethod(lambda ids, **k: activated.append(list(ids))),
    )
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"

    r.reactivate([{"id": "m--s1", "autostart_domains": [{"id": "d1", "was_on": True}]}])

    assert activated == []
    assert written == [
        ("m2--s9", {"autostart_domains": [{"id": "d1", "was_on": True}]})
    ]


def test_a_desktop_free_everywhere_gets_its_autostart_back(monkeypatch):
    class _Dom:
        def __init__(self, did):
            self.create_dict = {"hardware": {"disks": [{"storage_id": "s1"}]}}

    monkeypatch.setattr(mr, "Domain", _Dom)
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_storage",
        classmethod(
            lambda cls, sid: [
                {"id": "m--s1", "state": "released", "autostart_domains": []},
                {"id": "m0--s1", "state": "released", "autostart_domains": []},
            ]
        ),
    )
    activated = []
    monkeypatch.setattr(
        mr.DesktopEvents,
        "activate_autostart",
        staticmethod(lambda ids, **k: activated.append(list(ids))),
    )
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"

    r.reactivate([{"id": "m--s1", "autostart_domains": [{"id": "d1", "was_on": True}]}])

    assert activated == [["d1"]]
