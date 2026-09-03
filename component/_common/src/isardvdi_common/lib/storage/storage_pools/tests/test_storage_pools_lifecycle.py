#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the storage-pool enable/disable lifecycle added on top of the
governor refactor: the delete gate (pool must be **disabled and fully
drained**), the drain-status summary, and the queued-lane counting helper.

The guard (raise) paths never reach RethinkDB, so they are tested by stubbing
``StoragePool.get`` and the DB/redis-backed helper classmethods only.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.storage.storage_pools import storage_pools as mod

SPP = mod.StoragePoolsProcessed
DEFAULT = mod.DEFAULT_STORAGE_POOL_ID


def _patch_helpers(monkeypatch, pool, disks=0, queued=0, coverage=0, declared=None):
    monkeypatch.setattr(mod.StoragePool, "get", staticmethod(lambda _id: pool))
    monkeypatch.setattr(SPP, "_residing_disks", classmethod(lambda c, i, m=None: disks))
    monkeypatch.setattr(SPP, "_pending_lane_jobs", classmethod(lambda c, i: queued))
    monkeypatch.setattr(SPP, "_pool_coverage", classmethod(lambda c, i: coverage))
    monkeypatch.setattr(
        SPP,
        "_pool_coverage_declared",
        classmethod(lambda c, i: coverage if declared is None else declared),
    )


# --------------------------------------------------------------------------- #
# _lane_key_globs  (pure)
# --------------------------------------------------------------------------- #
def test_lane_globs_cover_own_and_move_lanes():
    globs = SPP._lane_key_globs("POOL")
    assert "rq:queue:storage.POOL.*" in globs  # own tier + per-category
    assert "rq:queue:storage.POOL:*" in globs  # move source
    assert "rq:queue:storage.*:POOL.*" in globs  # move destination


# --------------------------------------------------------------------------- #
# _pending_lane_jobs  (sums llen across matched lanes, dedup)
# --------------------------------------------------------------------------- #
def test_pending_lane_jobs_sums_llen(monkeypatch):
    redis = MagicMock()
    keys = {
        b"rq:queue:storage.POOL.*": [b"rq:queue:storage.POOL.reclaim"],
        b"rq:queue:storage.POOL:*": [b"rq:queue:storage.POOL:DST.maintenance"],
        b"rq:queue:storage.*:POOL.*": [b"rq:queue:storage.POOL.reclaim"],  # dup
    }
    redis.scan_iter.side_effect = lambda match, count=500: iter(keys.get(match, []))
    redis.llen.side_effect = lambda k: {
        b"rq:queue:storage.POOL.reclaim": 3,
        b"rq:queue:storage.POOL:DST.maintenance": 2,
    }[k]
    monkeypatch.setattr(mod.Task, "_redis", redis)
    # 3 (own reclaim, counted once despite the dup match) + 2 (move) = 5
    assert SPP._pending_lane_jobs("POOL") == 5


# --------------------------------------------------------------------------- #
# delete gate: disabled + drained
# --------------------------------------------------------------------------- #
def test_delete_default_pool_refused(monkeypatch):
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool(DEFAULT)
    assert e.value.args[0] == "bad_request"


def test_delete_requires_disabled_first(monkeypatch):
    _patch_helpers(monkeypatch, {"id": "p", "enabled": True, "categories": []})
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool("p")
    assert e.value.args[0] == "bad_request"
    assert "isable" in e.value.args[1]  # "Disable ... before deleting"


def test_delete_refused_with_categories(monkeypatch):
    _patch_helpers(monkeypatch, {"id": "p", "enabled": False, "categories": ["c1"]})
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool("p")
    assert "categories" in e.value.args[1]


def test_delete_refused_with_residing_disks(monkeypatch):
    _patch_helpers(
        monkeypatch, {"id": "p", "enabled": False, "categories": []}, disks=4
    )
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool("p")
    assert "disk" in e.value.args[1]


def test_delete_refused_when_not_drained(monkeypatch):
    _patch_helpers(
        monkeypatch,
        {"id": "p", "enabled": False, "categories": []},
        disks=0,
        queued=7,
    )
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool("p")
    assert "queued" in e.value.args[1]


def test_delete_missing_pool(monkeypatch):
    monkeypatch.setattr(mod.StoragePool, "get", staticmethod(lambda _id: None))
    with pytest.raises(Exception) as e:
        SPP.delete_storage_pool("gone")
    assert e.value.args[0] == "not_found"


# --------------------------------------------------------------------------- #
# pool_pending_summary  (drain-status)
# --------------------------------------------------------------------------- #
def test_pending_summary_drained_true_when_all_zero(monkeypatch):
    _patch_helpers(
        monkeypatch,
        {"id": "p", "enabled": False, "categories": [], "mountpoint": "/isard/x"},
        disks=0,
        queued=0,
        coverage=2,
    )
    s = SPP.pool_pending_summary("p")
    assert s == {
        "id": "p",
        "enabled": False,
        "categories": 0,
        "disks": 0,
        "queued_tasks": 0,
        "coverage": 2,
        "coverage_declared": 2,
        "drained": True,
    }


def test_pending_summary_not_drained_with_work(monkeypatch):
    _patch_helpers(
        monkeypatch,
        {"id": "p", "enabled": True, "categories": ["c"], "mountpoint": "/isard/x"},
        disks=1,
        queued=3,
        coverage=0,
    )
    s = SPP.pool_pending_summary("p")
    assert s["drained"] is False
    assert s["disks"] == 1 and s["queued_tasks"] == 3 and s["categories"] == 1
    assert s["enabled"] is True and s["coverage"] == 0


def test_pending_summary_missing_pool(monkeypatch):
    monkeypatch.setattr(mod.StoragePool, "get", staticmethod(lambda _id: None))
    with pytest.raises(Exception) as e:
        SPP.pool_pending_summary("gone")
    assert e.value.args[0] == "not_found"
