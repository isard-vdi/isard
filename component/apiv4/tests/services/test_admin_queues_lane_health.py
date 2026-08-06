#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The orphan-lane detector behind the storage-pool page.

An orphan lane is a storage queue holding jobs with no worker consuming it: its
tasks stall forever. The worker-centric ``get_consumers`` view cannot see one,
because it only enumerates queues that already have a worker -- so the question
has to be asked from the lane side.

It is asked with the primitives the shed gate already uses: one bounded
``SMEMBERS rq:queues`` for the lanes and ``served_coverage`` for the fleet.
Reading the keyspace instead would be a second, more expensive answer to a
question the fleet already answers -- and a wrong one in the case
``served_coverage`` exists to handle: a worker whose served set is not published
is a live consumer we cannot enumerate, never an absent one.
"""

import contextlib

import pytest
from api.services.admin import queues as mod

SVC = mod.AdminQueuesService


class _FakeRedis:
    """Enough redis for the two reads the detector makes.

    ``rq:queues`` is the set of ``rq:queue:<name>`` keys every queue registers
    itself in; lane depth is ``LLEN``. Fleet coverage is stubbed at the
    ``served_coverage`` boundary rather than rebuilt from worker hashes here --
    that function has its own tests, and duplicating its input format would
    couple this test to the fleet's storage layout.
    """

    def __init__(self, queues=None):
        self.queues = queues or {}  # lane name -> depth

    def smembers(self, key):
        if key in ("rq:queues", b"rq:queues"):
            return {f"rq:queue:{name}".encode() for name in self.queues}
        return set()

    def llen(self, key):
        name = key.decode() if isinstance(key, bytes) else key
        return self.queues.get(name.split("rq:queue:", 1)[-1], 0)

    def pipeline(self):
        outer = self

        class _Pipe:
            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def llen(self, key):
                self.calls.append(key)

            def execute(self):
                return [outer.llen(key) for key in self.calls]

        return _Pipe()


def _patch(monkeypatch, queues, covered=None, opaque=None):
    fake = _FakeRedis(queues=queues)

    @contextlib.contextmanager
    def _cm():
        yield fake

    monkeypatch.setattr(mod, "_connect_redis", _cm)
    monkeypatch.setattr(
        mod,
        "served_coverage",
        lambda conn: (covered or {}, opaque or set()),
    )
    return fake


# --------------------------------------------------------------------------- #
# the fail-open case: an unreadable consumer is not an absent one
# --------------------------------------------------------------------------- #
def test_a_pool_whose_coverage_is_unknown_is_not_called_orphan(monkeypatch):
    """A worker that has not published its served set still drains the lane.

    Calling that pool orphaned sends an operator to restart a consumer that is
    already running -- and on the storage-pool page it reads as "this pool is
    dead", which is the opposite of the truth.
    """
    _patch(
        monkeypatch,
        queues={"storage.OPAQUE.reclaim": 7},
        covered={},  # nothing enumerable...
        opaque={"OPAQUE"},  # ...but a live worker is there
    )

    out = SVC.get_storage_lane_health()

    assert out["healthy"] is True
    assert out["orphan_pools"] == []


# --------------------------------------------------------------------------- #
# orphan detection
# --------------------------------------------------------------------------- #
def test_all_served_is_healthy(monkeypatch):
    _patch(
        monkeypatch,
        queues={"storage.POOL.reclaim": 5},
        covered={("POOL", "interactive"): 3},  # any lane of the pool counts
    )

    out = SVC.get_storage_lane_health()

    assert out["healthy"] is True
    assert out["orphans"] == [] and out["orphan_pools"] == []


def test_flags_the_orphan_pool_and_rolls_its_lanes_up(monkeypatch):
    _patch(
        monkeypatch,
        queues={
            "storage.ORPH.reclaim": 4,
            "storage.ORPH.CAT.maintenance": 2,  # same pool, per-category lane
            "storage.SERVED.reclaim": 9,
        },
        covered={("SERVED", "interactive"): 5},
    )

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


def test_a_cross_pool_move_lane_keeps_its_src_dst_identity(monkeypatch):
    """Migration runs on ``storage.<src>:<dst>.<tier>``; a stranded one is the
    failure that leaves a migration hanging with no consumer to finish it."""
    _patch(monkeypatch, queues={"storage.SRC:DST.maintenance": 3}, covered={})

    assert SVC.get_storage_lane_health()["orphan_pools"] == ["SRC:DST"]


def test_an_empty_lane_is_not_an_orphan(monkeypatch):
    """No queued work means nothing is stalling, worker or not."""
    _patch(monkeypatch, queues={"storage.POOL.reclaim": 0}, covered={})

    assert SVC.get_storage_lane_health()["healthy"] is True


def test_orphans_come_back_worst_first(monkeypatch):
    _patch(
        monkeypatch,
        queues={"storage.SMALL.reclaim": 1, "storage.BIG.reclaim": 40},
        covered={},
    )

    assert SVC.get_storage_lane_health()["orphan_pools"] == ["BIG", "SMALL"]


# --------------------------------------------------------------------------- #
# bounded, and honest about it
# --------------------------------------------------------------------------- #
def test_the_lane_cap_is_reported_not_silent(monkeypatch):
    """The snapshot keeps the busiest ``MAX_LANES``. A caller that cannot tell
    a truncated scan from a complete one reads "healthy" as "all clear"."""
    monkeypatch.setattr(mod, "MAX_LANES", 2)
    _patch(
        monkeypatch,
        queues={f"storage.P{i}.reclaim": i + 1 for i in range(5)},
        covered={},
    )

    out = SVC.get_storage_lane_health()

    assert out["truncated_lanes"] == 3
    assert len(out["orphan_pools"]) == 2


def test_a_redis_failure_fails_open(monkeypatch):
    """The detector is advisory. It must never turn a redis blip into a page
    full of pools reported dead."""

    @contextlib.contextmanager
    def _boom():
        raise ConnectionError("redis is gone")
        yield  # pragma: no cover

    monkeypatch.setattr(mod, "_connect_redis", _boom)

    out = SVC.get_storage_lane_health()

    assert out["healthy"] is True
    assert out["orphan_pools"] == []
    assert out["coverage_known"] is False


def test_a_healthy_answer_says_its_coverage_was_readable(monkeypatch):
    _patch(monkeypatch, queues={"storage.POOL.reclaim": 0}, covered={})

    assert SVC.get_storage_lane_health()["coverage_known"] is True


# --------------------------------------------------------------------------- #
# no second detector
# --------------------------------------------------------------------------- #
def test_the_detector_does_not_walk_the_keyspace(monkeypatch):
    """``scan_iter`` over ``rq:queue:storage.*`` answers the same question as
    the registry read, at the cost of a keyspace walk plus a round trip per
    queue -- on the admin page of an install with thousands of lanes."""
    fake = _patch(monkeypatch, queues={"storage.POOL.reclaim": 2}, covered={})

    def _forbidden(*a, **kw):
        pytest.fail("the detector walked the keyspace instead of rq:queues")

    fake.scan_iter = _forbidden

    SVC.get_storage_lane_health()
