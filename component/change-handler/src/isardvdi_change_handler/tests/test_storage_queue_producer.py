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


def _task(tid, user, tier="standard", storage_id=None):
    """A Task double. ``storage_id`` is the row that created the chain, read off
    the job's own meta now that the ``task`` secondary index is retired; ``None``
    stands for a task no row owns."""
    return SimpleNamespace(
        id=tid,
        user_id=user,
        queue=f"storage.{DEF}.{tier}",
        position=1,
        task="resize",
        storage_id=storage_id if storage_id is not None else f"stg-{tid}",
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

    with patch.object(sqp, "Queue", _Queue), patch.object(
        sqp, "Task", lambda jid: tasks[jid]
    ), patch.object(sqp.queue_estimate, "estimate_task", lambda t, c=None: ests[t.id]):
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
    # a task whose job meta names no owner row: the frontend could not map it
    # to a card, so it is dropped rather than emitted half-resolved
    tasks = {"t1": _task("t1", "user-a", storage_id="")}
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

    with patch.object(sqp, "Queue", _Queue), patch.object(
        sqp, "Task", lambda jid: tasks[jid]
    ), patch.object(sqp.queue_estimate, "estimate_task", lambda t, c=None: ests[t.id]):
        out = sqp._collect(conn)
    assert out == []


def _owner_task(tid, user, *, storage_id=None, media_id=None, tier="maintenance"):
    """A Task double that names its owner the way the real one does.

    A task belongs to a disk OR to a media, never both: the disk id comes back
    from ``Task.storage_id``, the media id is stamped on the job's own meta by
    ``Media.create_task``, which never sets a storage id at all.
    """
    return SimpleNamespace(
        id=tid,
        user_id=user,
        queue=f"storage.{DEF}.{tier}",
        position=1,
        task="download_url",
        storage_id=storage_id,
        job=SimpleNamespace(meta={"storage_id": storage_id, "media_id": media_id}),
    )


def _queued_est(position=3):
    return {
        "effective_position": position,
        "eta_seconds": None,
        "has_consumer": True,
        "stranded": False,
    }


def test_a_queued_media_download_is_emitted_with_its_media_id():
    """A media download shows no queue position at all while it waits.

    A download is among the longest waits a user ever has, so it is exactly the
    case a position is worth showing -- and the media row is the only handle the
    frontend has to put it on, because a media task names no disk.
    """
    conn = _Conn({f"storage.{DEF}.maintenance"})
    jobs = {f"storage.{DEF}.maintenance": ["t1"]}
    tasks = {"t1": _owner_task("t1", "user-a", media_id="m-1")}
    out = _run_collect(conn, jobs, tasks, {"t1": _queued_est(3)})
    assert len(out) == 1
    user, payload = out[0]
    assert user == "user-a"
    assert payload["media_id"] == "m-1"
    assert payload["effective_position"] == 3
    assert payload["status"] == "queued" and payload["pending"] is True


def test_a_queued_disk_task_still_names_its_disk():
    """The disk case is the one that already worked; teaching the sweep about
    media must not cost it."""
    conn = _Conn({f"storage.{DEF}.maintenance"})
    jobs = {f"storage.{DEF}.maintenance": ["t1"]}
    tasks = {"t1": _owner_task("t1", "user-a", storage_id="s-1")}
    out = _run_collect(conn, jobs, tasks, {"t1": _queued_est(3)})
    assert len(out) == 1
    payload = out[0][1]
    assert payload["storage_id"] == "s-1"
    assert payload.get("media_id") is None


def test_a_task_naming_neither_owner_is_still_dropped():
    """Nothing on screen could carry it, so emitting it would only add a card-less
    event to every sweep."""
    conn = _Conn({f"storage.{DEF}.maintenance"})
    jobs = {f"storage.{DEF}.maintenance": ["t1"]}
    tasks = {"t1": _owner_task("t1", "user-a")}
    out = _run_collect(conn, jobs, tasks, {"t1": _queued_est(3)})
    assert out == []
