#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for the storage-queue position producer's pure sweep logic.

Pins that ``_storage_lanes`` filters ``rq:queues`` to storage lanes and that
``_collect`` emits only genuinely-waiting tasks (queued-with-position or
stranded), skips the scheduler user, batch-resolves storage ids, and drops a
task whose storage id cannot be resolved.
"""

from types import SimpleNamespace
from unittest.mock import patch

from isardvdi_change_handler.streams import storage_queue_producer as sqp

DEF = "00000000-0000-0000-0000-000000000000"


class _Conn:
    def __init__(self, lanes):
        self._lanes = set(lanes)

    def smembers(self, key):
        return set(self._lanes)


def _task(tid, user, tier="standard"):
    return SimpleNamespace(
        id=tid, user_id=user, queue=f"storage.{DEF}.{tier}", position=1, task="resize"
    )


def test_storage_lanes_filters_and_strips_prefix():
    conn = _Conn(
        {
            f"rq:queue:storage.{DEF}.standard",  # prefixed key form
            "rq:queue:notifier",  # non-storage -> dropped
            f"storage.{DEF}.interactive",  # bare name form
        }
    )
    lanes = sqp._storage_lanes(conn)
    assert f"storage.{DEF}.standard" in lanes
    assert f"storage.{DEF}.interactive" in lanes
    assert not any("notifier" in lane for lane in lanes)


def _run_collect(conn, jobs, tasks, ests):
    class _Queue:
        def __init__(self, lane, connection=None):
            self.lane = lane

        def get_job_ids(self, start, end):
            return jobs.get(self.lane, [])

    class _Storage:
        @staticmethod
        def get_storage_ids_from_task_ids(ids):
            return [{"task_id": i, "storage_id": f"stg-{i}"} for i in ids]

    with patch.object(sqp, "Queue", _Queue), patch.object(
        sqp, "Task", lambda jid: tasks[jid]
    ), patch.object(sqp, "Storage", _Storage), patch.object(
        sqp.queue_estimate, "estimate_task", lambda t, c=None: ests[t.id]
    ):
        return sqp._collect(conn)


def test_collect_emits_only_waiting_tasks_and_skips_scheduler():
    conn = _Conn({f"storage.{DEF}.standard"})
    jobs = {f"storage.{DEF}.standard": ["t1", "t2", "sched"]}
    tasks = {
        "t1": _task("t1", "user-a"),
        "t2": _task("t2", "user-b"),
        "sched": _task("sched", "isard-scheduler"),
    }
    ests = {
        "t1": {  # queued with a position -> emitted
            "effective_position": 5,
            "eta_seconds": 100.0,
            "has_consumer": True,
            "stranded": False,
        },
        "t2": {  # running / not waiting -> skipped
            "effective_position": None,
            "eta_seconds": None,
            "has_consumer": True,
            "stranded": False,
        },
    }
    out = _run_collect(conn, jobs, tasks, ests)
    assert len(out) == 1
    user, payload = out[0]
    assert user == "user-a"
    assert payload["id"] == "t1"
    assert payload["storage_id"] == "stg-t1"
    assert payload["effective_position"] == 5
    assert payload["eta_seconds"] == 100.0
    assert payload["status"] == "queued" and payload["pending"] is True


def test_collect_includes_stranded_without_position():
    conn = _Conn({f"storage.{DEF}.interactive"})
    jobs = {f"storage.{DEF}.interactive": ["t1"]}
    tasks = {"t1": _task("t1", "user-a", tier="interactive")}
    ests = {
        "t1": {
            "effective_position": None,
            "eta_seconds": None,
            "has_consumer": False,
            "stranded": True,
        }
    }
    out = _run_collect(conn, jobs, tasks, ests)
    assert len(out) == 1 and out[0][1]["stranded"] is True


def test_collect_drops_task_without_resolvable_storage_id():
    conn = _Conn({f"storage.{DEF}.standard"})
    jobs = {f"storage.{DEF}.standard": ["t1"]}
    tasks = {"t1": _task("t1", "user-a")}
    ests = {
        "t1": {
            "effective_position": 2,
            "eta_seconds": None,
            "has_consumer": True,
            "stranded": False,
        }
    }

    class _Queue:
        def __init__(self, lane, connection=None):
            self.lane = lane

        def get_job_ids(self, start, end):
            return jobs.get(self.lane, [])

    class _StorageNoMatch:
        @staticmethod
        def get_storage_ids_from_task_ids(ids):
            return []  # no storage owns this task

    with patch.object(sqp, "Queue", _Queue), patch.object(
        sqp, "Task", lambda jid: tasks[jid]
    ), patch.object(sqp, "Storage", _StorageNoMatch), patch.object(
        sqp.queue_estimate, "estimate_task", lambda t, c=None: ests[t.id]
    ):
        out = sqp._collect(conn)
    assert out == []
