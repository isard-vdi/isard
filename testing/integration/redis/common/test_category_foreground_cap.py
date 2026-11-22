# SPDX-License-Identifier: AGPL-3.0-or-later

"""The per-category foreground cap, asserted on the real Redis server.

A flat foreground lane is shared by every category, so filling it with one
category up to that category's share must refuse only that category while
another still enqueues, and the global cap must still bound the sum. The unit
suite proves the decision with a fake connection; this proves it against the
LRANGE/MGET/SET the real server runs, whose byte replies the fake never gives.
"""

import time

import pytest
from isardvdi_common.lib import queue_coverage as qc

POOL = "00000000-0000-0000-0000-000000000000"
TIER = "interactive"
LANE = f"storage.{POOL}.{TIER}"


def _live_consumer(conn):
    conn.zadd(qc.cov_key(POOL, TIER), {"worker-7850-it": time.time()})
    conn.expire(qc.cov_key(POOL, TIER), 300)


def _enqueue(conn, category, count):
    for i in range(count):
        job_id = f"{category}-{i}"
        conn.rpush(qc._RQ_QUEUE_PREFIX + LANE, job_id)
        qc.note_pending_category(conn, LANE, job_id, category)


def test_a_category_at_its_cap_refuses_only_itself(scratch_redis):
    _live_consumer(scratch_redis)
    _enqueue(scratch_redis, "catA", qc.category_hard_cap(TIER))

    decision, ctx = qc.lane_shed_decision(scratch_redis, LANE, category="catA")
    assert decision == "reject"
    assert ctx["reason"] == qc.REASON_CATEGORY_OVERLOADED
    assert ctx["category"] == "catA"

    decision, _ctx = qc.lane_shed_decision(scratch_redis, LANE, category="catB")
    assert decision != "reject"


def test_check_shed_429s_the_capped_category_and_admits_another(scratch_redis):
    _live_consumer(scratch_redis)
    _enqueue(scratch_redis, "catA", qc.category_hard_cap(TIER))

    with pytest.raises(Exception) as excinfo:
        qc.check_shed(scratch_redis, LANE, category="catA")
    assert getattr(excinfo.value, "status_code", None) == 429
    assert getattr(excinfo.value, "error", {}).get("description_code") == (
        "storage_overloaded_retry_later"
    )

    qc.check_shed(scratch_redis, LANE, category="catB")  # admitted -> no raise


def test_the_global_cap_still_refuses_a_fresh_category_when_full(scratch_redis):
    _live_consumer(scratch_redis)
    gcap, ccap = qc.hard_cap(TIER), qc.category_hard_cap(TIER)
    remaining, idx = gcap, 0
    while remaining > 0:
        take = min(ccap - 1, remaining)
        _enqueue(scratch_redis, f"cat{idx}", take)
        remaining -= take
        idx += 1

    decision, ctx = qc.lane_shed_decision(scratch_redis, LANE, category="fresh")
    assert decision == "reject"
    assert ctx["reason"] == qc.REASON_OVERLOADED


def _storage_task(category, storage_id):
    """A real ``Storage.create_task``; only the owner's category lookup is replaced."""
    from unittest.mock import PropertyMock, patch

    from isardvdi_common.models.storage import Storage

    storage = Storage.__new__(Storage)
    object.__setattr__(storage, "id", storage_id)
    object.__setattr__(storage, "user_id", f"user-{category}")
    with patch.object(
        Storage, "category", new_callable=PropertyMock, return_value=category
    ):
        return storage.create_task(
            user_id=f"user-{category}",
            queue=LANE,
            task="qemu_img_info",
            job_kwargs={"kwargs": {"storage_id": storage_id}},
        )


def test_a_real_enqueue_indexes_its_category_and_is_capped(
    task_on_scratch_redis, monkeypatch
):
    """a main: no storage:jobcat index is written, so one category fills the lane."""
    from isardvdi_common.lib import governor_counters
    from isardvdi_common.models.task import Task

    monkeypatch.setenv("STORAGE_SHED_CAT_HARD_INTERACTIVE", "2")
    conn = task_on_scratch_redis
    _live_consumer(conn)

    admitted = [_storage_task("catA", f"test-7850-a{i}") for i in range(2)]
    for task_id in admitted:
        assert (
            Task(task_id).job.origin == LANE
        ), f"{task_id} landed on {Task(task_id).job.origin}, not the flat {LANE}"
        indexed = conn.get(f"storage:jobcat:{task_id}")
        assert (
            indexed == b"catA"
        ), f"expected storage:jobcat:{task_id} == b'catA', got {indexed!r}"

    with pytest.raises(Exception) as excinfo:
        _storage_task("catA", "test-7850-a2")
    assert (
        getattr(excinfo.value, "status_code", None) == 429
    ), f"expected a 429 for the capped category, got {excinfo.value!r}"
    by_reason = governor_counters.read_shed(conn)["by_reason"]
    assert by_reason == {
        qc.REASON_CATEGORY_OVERLOADED: 1
    }, f"expected one category_overloaded shed, got {by_reason}"
    assert conn.llen(qc._RQ_QUEUE_PREFIX + LANE) == 2, "the refused task was queued"

    other = _storage_task("catB", "test-7850-b0")
    assert conn.get(f"storage:jobcat:{other}") == b"catB"
