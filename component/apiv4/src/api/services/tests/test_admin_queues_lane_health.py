#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the lane-centric orphan-lane detector and the move-lane-safe
worker parse added to ``AdminQueuesService``.

An orphan lane is a storage queue holding jobs with no worker consuming it;
the pre-existing worker-centric ``get_consumers`` view cannot see it, so a
lane-centric scan was added.
"""

import contextlib

from api.services.admin import queues as mod

SVC = mod.AdminQueuesService


class _FakeRedis:
    """Minimal redis stub: ``rq:queue:<name>`` are lists (llen), ``rq:workers:
    <name>`` are sets (scard). scan_iter globs on a literal '.' + trailing '*'."""

    def __init__(self, queues=None, workers=None):
        self.queues = queues or {}  # name -> depth
        self.workers = workers or {}  # name -> member count

    def scan_iter(self, match=b"", count=1000):
        prefix = match.decode().rstrip("*")
        if prefix.startswith("rq:queue:"):
            base = prefix[len("rq:queue:") :]
            for name, depth in self.queues.items():
                if name.startswith(base):
                    yield f"rq:queue:{name}".encode()
        elif prefix.startswith("rq:workers:"):
            base = prefix[len("rq:workers:") :]
            for name, n in self.workers.items():
                if name.startswith(base):
                    yield f"rq:workers:{name}".encode()

    def llen(self, key):
        return self.queues.get(key.decode().split("rq:queue:", 1)[1], 0)

    def scard(self, key):
        return self.workers.get(key.decode().split("rq:workers:", 1)[1], 0)


def _patch_redis(monkeypatch, fake):
    @contextlib.contextmanager
    def _cm():
        yield fake

    monkeypatch.setattr(mod, "_connect_redis", _cm)


# --------------------------------------------------------------------------- #
# _lane_pool_prefix  (pure)
# --------------------------------------------------------------------------- #
def test_lane_pool_prefix_plain_and_category_and_move():
    assert SVC._lane_pool_prefix("storage.POOL.reclaim") == "POOL"
    # per-category sub-lane collapses to the pool (so a pool-lane worker covers it)
    assert SVC._lane_pool_prefix("storage.POOL.CAT.reclaim") == "POOL"
    # cross-pool move lane keeps the src:dst identity (matched on both sides)
    assert SVC._lane_pool_prefix("storage.SRC:DST.maintenance") == "SRC:DST"


# --------------------------------------------------------------------------- #
# get_storage_lane_health  (orphan detection)
# --------------------------------------------------------------------------- #
def test_lane_health_all_served_is_healthy(monkeypatch):
    fake = _FakeRedis(
        queues={"storage.POOL.reclaim": 5},
        workers={"storage.POOL.interactive": 3},  # POOL is served
    )
    _patch_redis(monkeypatch, fake)
    out = SVC.get_storage_lane_health()
    assert out["healthy"] is True
    assert out["orphans"] == [] and out["orphan_pools"] == []


def test_lane_health_flags_orphan_pool(monkeypatch):
    fake = _FakeRedis(
        queues={
            "storage.ORPH.reclaim": 4,
            "storage.ORPH.CAT.maintenance": 2,  # same pool, per-category
            "storage.SERVED.reclaim": 9,
        },
        workers={"storage.SERVED.interactive": 5},  # only SERVED has a worker
    )
    _patch_redis(monkeypatch, fake)
    out = SVC.get_storage_lane_health()
    assert out["healthy"] is False
    assert out["orphan_pools"] == ["ORPH"]
    orph = out["orphans"][0]
    assert orph["pool"] == "ORPH"
    assert orph["queued"] == 6  # 4 + 2 across the pool's lanes
    assert {lane["queue"] for lane in orph["lanes"]} == {
        "storage.ORPH.reclaim",
        "storage.ORPH.CAT.maintenance",
    }


def test_lane_health_empty_lanes_ignored(monkeypatch):
    # a lane with 0 depth is not an orphan even with no worker
    fake = _FakeRedis(queues={"storage.POOL.reclaim": 0}, workers={})
    _patch_redis(monkeypatch, fake)
    assert SVC.get_storage_lane_health()["healthy"] is True


def test_lane_health_worker_set_with_zero_members_not_served(monkeypatch):
    # a stale rq:workers set with 0 members does not count as serving
    fake = _FakeRedis(
        queues={"storage.POOL.reclaim": 3},
        workers={"storage.POOL.reclaim": 0},
    )
    _patch_redis(monkeypatch, fake)
    out = SVC.get_storage_lane_health()
    assert out["orphan_pools"] == ["POOL"]
