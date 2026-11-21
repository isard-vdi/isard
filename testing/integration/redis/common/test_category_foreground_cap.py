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
