# SPDX-License-Identifier: AGPL-3.0-or-later

"""A mass disk action kept in redis: every disk is tried once, and a restart resumes where it stopped."""

from unittest.mock import MagicMock

import pytest
from api.services import storage_batches
from tests.services.fake_redis import FakeRedis

PAYLOAD = {"user_id": "u-admin", "role_id": "admin", "category_id": "default"}


class _Crash(BaseException):
    """The process dies: nothing in the runner catches it."""


@pytest.fixture
def batches(monkeypatch):
    redis = FakeRedis()
    spawned = []
    notify = MagicMock()
    monkeypatch.setattr(storage_batches, "_redis", lambda: redis)
    monkeypatch.setattr(storage_batches, "_spawn", lambda b, o: spawned.append((b, o)))
    monkeypatch.setattr(storage_batches, "notify_admin", notify)
    monkeypatch.setattr(storage_batches, "_ACTIONS", {})
    return redis, spawned, notify


def _register(tried, refuse=(), crash_at=None):
    def outcome(payload, storage_id):
        tried.append(storage_id)
        if storage_id == crash_at and tried.count(storage_id) == 1:
            raise _Crash()
        if storage_id in refuse:
            return {
                "storage_id": storage_id,
                "description_code": "storage_open_not_checkable",
            }
        return {"storage_id": storage_id, "task_id": f"t-{storage_id}"}

    storage_batches.register("check", "Integrity checks of the {status} disks", outcome)


def _run_spawned(spawned):
    while spawned:
        storage_batches.run(*spawned.pop(0))


def test_the_answer_counts_distinct_disks_and_the_run_starts_once(batches):
    redis, spawned, notify = batches
    _register([])
    assert storage_batches.start(PAYLOAD, "check", "ready", ["a", "b", "a"]) == 2
    assert len(spawned) == 1
    notify.assert_not_called()


def test_every_disk_is_tried_and_the_notice_sums_them_up(batches):
    redis, spawned, notify = batches
    tried = []
    _register(tried, refuse={"b", "c"})
    storage_batches.start(PAYLOAD, "check", "ready", ["a", "b", "c"])
    _run_spawned(spawned)
    assert tried == ["a", "b", "c"]
    user_id, title, text = notify.call_args.args
    assert (user_id, title) == ("u-admin", "Integrity checks of the ready disks")
    assert (
        text
        == "Queued on 1 of 3 disk(s).\n2 refused: storage_open_not_checkable (b, c)"
    )
    assert notify.call_args.kwargs == {"type": "info", "params": {"hide": False}}
    assert redis.data == {"storage:batches": set()}


def test_the_notice_of_a_big_batch_stays_short(batches):
    redis, spawned, notify = batches
    ids = [f"s{i}" for i in range(4000)]
    _register([], refuse=set(ids[1000:]))
    storage_batches.start(PAYLOAD, "check", "ready", ids)
    _run_spawned(spawned)
    text = notify.call_args.args[2]
    assert text == (
        "Queued on 1000 of 4000 disk(s).\n"
        "3000 refused: storage_open_not_checkable (s1000, s1001, s1002, ...)"
    )


def test_a_restart_mid_batch_resumes_where_it_stopped(batches):
    redis, spawned, notify = batches
    tried = []
    _register(tried, crash_at="c")
    storage_batches.start(PAYLOAD, "check", "ready", ["a", "b", "c", "d", "e"])
    with pytest.raises(_Crash):
        _run_spawned(spawned)
    notify.assert_not_called()
    storage_batches.resume_all()
    assert spawned == [], "the dead runner's lease still holds"
    redis.delete(
        "storage:batch:"
        + next(iter(redis.smembers("storage:batches"))).decode()
        + ":lease"
    )
    storage_batches.resume_all()
    _run_spawned(spawned)
    assert tried == ["a", "b", "c", "c", "d", "e"]
    assert notify.call_args.args[2] == "Queued on 5 of 5 disk(s)."
    assert notify.call_count == 1


def test_a_runner_that_lost_its_lease_stops(batches):
    redis, spawned, notify = batches
    tried = []
    _register(tried)
    storage_batches.start(PAYLOAD, "check", "ready", ["a", "b"])
    batch_id, _owner = spawned.pop()
    storage_batches.run(batch_id, "someone-else")
    assert tried == []
    notify.assert_not_called()


def test_a_failing_batch_says_it_resumes_and_gives_up_in_the_end(batches, monkeypatch):
    redis, spawned, notify = batches

    def broken(payload, storage_id):
        raise RuntimeError("redis went away")

    storage_batches.register("check", "Checks of the {status} disks", broken)
    storage_batches.start(PAYLOAD, "check", "ready", ["a"])
    batch_id, owner = spawned.pop()
    for _ in range(storage_batches.MAX_ATTEMPTS - 1):
        storage_batches.run(batch_id, owner)
        assert notify.call_args.kwargs["type"] == "warning"
        assert "resumes on its own" in notify.call_args.args[2]
    storage_batches.run(batch_id, owner)
    assert notify.call_args.kwargs["type"] == "error"
    assert redis.data == {"storage:batches": set()}


def test_an_expired_batch_leaves_the_index(batches):
    redis, spawned, notify = batches
    redis.sadd("storage:batches", "gone")
    storage_batches.resume_all()
    assert redis.smembers("storage:batches") == set()
    assert spawned == []


def test_the_lifespan_loop_resumes_the_stored_batches(monkeypatch):
    import asyncio

    import api

    calls = []
    monkeypatch.setattr(storage_batches, "resume_all", lambda: calls.append(1))

    async def stop(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(api.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(api._resume_storage_batches())
    assert calls == [1]
