#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for queue_estimate.estimate_task.

effective_position must add the backlog of higher-priority tiers in the same
pool to the raw job position, be None when the job is not queued, and never
raise.
"""

import json

from isardvdi_common.lib import queue_estimate as qe

DEF = "00000000-0000-0000-0000-000000000000"


class _FakeRedis:
    def __init__(self):
        self.sets = {}
        self.hashes = {}
        self.lists = {}
        self.kv = {}
        self.fail = False

    def smembers(self, key):
        return set(self.sets.get(key, ()))

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def llen(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.lists.get(key, 0)

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, ex=None):
        self.kv[key] = value
        return True

    def pipeline(self):
        redis = self

        class _Pipe:
            def __init__(self):
                self._ops = []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def hgetall(self, key):
                self._ops.append(key)
                return self

            def execute(self):
                return [redis.hgetall(k) for k in self._ops]

        return _Pipe()


class _FakeTask:
    def __init__(self, redis, queue, position, action="create"):
        self._redis = redis
        self.queue = queue
        self.position = position
        self.task = action


def _governed_worker(r, name=DEF):
    lanes = [
        f"storage.{DEF}.{t}"
        for t in ("interactive", "standard", "maintenance", "background")
    ]
    r.sets.setdefault("rq:workers", set()).add(f"rq:worker:{name}")
    r.hashes[f"rq:worker:{name}"] = {"queues": ",".join(lanes)}
    r.hashes[f"governor:worker:{name}"] = {"served_lanes": json.dumps(lanes)}


def test_effective_position_adds_higher_tier_backlog():
    r = _FakeRedis()
    _governed_worker(r)
    # 3 ahead in interactive + 2 in standard; our task sits in maintenance at
    # raw position 4 -> effective 3 + 2 + 4 = 9
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = 3
    r.lists[f"rq:queue:storage.{DEF}.standard"] = 2
    task = _FakeTask(r, f"storage.{DEF}.maintenance", position=4)
    out = qe.estimate_task(task)
    assert out["effective_position"] == 9
    assert out["eta_seconds"] is None  # ETA lands with the EWMA writer later


def test_top_tier_effective_position_equals_raw():
    r = _FakeRedis()
    _governed_worker(r)
    task = _FakeTask(r, f"storage.{DEF}.interactive", position=2)
    out = qe.estimate_task(task)
    assert out["effective_position"] == 2  # nothing outranks interactive


def test_position_none_when_not_queued():
    r = _FakeRedis()
    _governed_worker(r)
    task = _FakeTask(r, f"storage.{DEF}.standard", position=None)
    out = qe.estimate_task(task)
    assert out["effective_position"] is None


def test_coverage_flags_populated():
    r = _FakeRedis()
    _governed_worker(r)
    task = _FakeTask(r, f"storage.{DEF}.standard", position=0)
    out = qe.estimate_task(task)
    assert out["has_consumer"] is True
    assert out["stranded"] is False


def test_non_storage_queue_all_none():
    out = qe.estimate_task(_FakeTask(_FakeRedis(), "notifier", position=1))
    assert out == {
        "effective_position": None,
        "eta_seconds": None,
        "has_consumer": None,
        "stranded": None,
    }


def test_never_raises_and_degrades_on_redis_error():
    r = _FakeRedis()
    _governed_worker(r)
    r.fail = True
    task = _FakeTask(r, f"storage.{DEF}.maintenance", position=1)
    out = qe.estimate_task(task)  # llen raises per-lane -> swallowed, no crash
    # higher-tier backlog degrades to 0, so we still surface the raw position
    assert out["effective_position"] == 1


# --- EWMA service time + ETA -----------------------------------------------


def test_record_service_time_then_eta_uses_it():
    r = _FakeRedis()
    _governed_worker(r)  # 1 worker serves standard -> eff_conc 1
    qe.record_service_time(r, "standard", "resize", 30.0)
    # position 4 in standard, one worker -> eta ceil(4/1) * 30 = 120
    task = _FakeTask(r, f"storage.{DEF}.standard", position=4, action="resize")
    out = qe.estimate_task(task)
    assert out["effective_position"] == 4
    assert out["eta_seconds"] == 120.0


def test_eta_divides_by_effective_concurrency():
    r = _FakeRedis()
    for n in range(4):  # 4 workers serve the standard lane
        _governed_worker(r, name=f"w{n}")
    qe.record_service_time(r, "standard", "resize", 40.0)
    task = _FakeTask(r, f"storage.{DEF}.standard", position=8, action="resize")
    out = qe.estimate_task(task)
    # ceil(8 / 4) * 40 = 80
    assert out["eta_seconds"] == 80.0


def test_eta_none_without_a_sample():
    r = _FakeRedis()
    _governed_worker(r)
    task = _FakeTask(r, f"storage.{DEF}.standard", position=3, action="resize")
    assert qe.estimate_task(task)["eta_seconds"] is None


def test_record_service_time_ignores_noise_and_clamps_outliers():
    r = _FakeRedis()
    qe.record_service_time(r, "standard", "resize", 0.01)  # sub-50ms ignored
    assert r.get(qe._ewma_key("standard", "resize")) is None
    qe.record_service_time(r, "standard", "resize", 999999.0)  # clamped
    assert float(r.get(qe._ewma_key("standard", "resize"))) == qe._SVC_MAX


def test_ewma_smooths_successive_samples():
    r = _FakeRedis()
    qe.record_service_time(r, "standard", "resize", 10.0)  # first -> 10
    qe.record_service_time(r, "standard", "resize", 20.0)  # 0.2*20 + 0.8*10 = 12
    assert abs(float(r.get(qe._ewma_key("standard", "resize"))) - 12.0) < 1e-9
