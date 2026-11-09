# SPDX-License-Identifier: AGPL-3.0-or-later

"""The sweep reaches past blocked disks at the head of a queue, prefers the
cheaper action, counts the bytes each action reads, and scans zeros."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.services.storage import StorageService

ADMIN = {"user_id": "u-admin", "role_id": "admin", "category_id": "default"}
GIB = 1 << 30


def _disk(sid, size=GIB, marks=None, started=False):
    storage = MagicMock(id=sid)
    setattr(storage, "qemu-img-info", {"actual-size": size})
    storage.pending_actions = marks or {}
    storage.domains = [SimpleNamespace(status="Started")] if started else []
    return storage


@pytest.fixture
def estate():
    disks = {}
    parents = set()

    def children(ids, include_deleted=False):
        return [SimpleNamespace(parent=i) for i in ids if i in parents]

    enqueued = []
    with (
        patch("api.services.storage.get_storage", lambda p, sid: disks[sid]),
        patch("api.services.storage.Storage.get_children", side_effect=children),
        patch(
            "api.services.storage.StorageService._sweep_enqueue",
            side_effect=lambda u, action, s: enqueued.append((action, s.id)),
        ),
    ):
        yield SimpleNamespace(disks=disks, parents=parents, enqueued=enqueued)


def test_blocked_bases_at_the_head_do_not_starve_the_leaves_behind_them(estate):
    ids = [f"base{i}" for i in range(60)] + [f"leaf{i}" for i in range(5)]
    for sid in ids:
        estate.disks[sid] = _disk(sid)
    estate.parents.update(i for i in ids if i.startswith("base"))
    out = StorageService._sweep_act(
        ADMIN, "dig_holes", ids, {"disks": 50, "bytes": None}
    )
    assert out["selected"] == 5
    assert out["skipped_has_descendants"] == 60
    assert [sid for _, sid in estate.enqueued] == [f"leaf{i}" for i in range(5)]


def test_started_disks_at_the_head_do_not_starve_the_rest(estate):
    ids = [f"run{i}" for i in range(3)] + ["idle"]
    for sid in ids:
        estate.disks[sid] = _disk(sid, started=sid != "idle")
    out = StorageService._sweep_act(ADMIN, "sparsify", ids, {"disks": 1, "bytes": None})
    assert (out["selected"], out["skipped_started"]) == (1, 3)


def test_the_disk_budget_stops_the_walk(estate):
    ids = [f"leaf{i}" for i in range(200)]
    for sid in ids:
        estate.disks[sid] = _disk(sid)
    budget = {"disks": 50, "bytes": None}
    out = StorageService._sweep_act(ADMIN, "sparsify", ids, budget)
    assert out["selected"] == 50 and budget["disks"] == 0
    assert out["examined"] == 50 and out["skipped_budget"] == 150


def test_a_verified_dig_spends_three_times_its_size(estate):
    for sid in ("a", "b"):
        estate.disks[sid] = _disk(sid, size=GIB)
    budget = {"disks": None, "bytes": 4 * GIB}
    out = StorageService._sweep_act(ADMIN, "dig_holes", ["a", "b"], budget)
    assert out["selected"] == 1 and budget["bytes"] == GIB


def test_a_disk_that_also_needs_a_dig_is_left_to_the_dig(estate):
    estate.disks["both"] = _disk("both", marks={"sparsify": {}, "dig_holes": {}})
    estate.disks["only"] = _disk("only", marks={"sparsify": {}})
    out = StorageService._sweep_act(
        ADMIN,
        "sparsify",
        ["both", "only"],
        {"disks": None, "bytes": None},
        {"dig_holes"},
    )
    assert out["skipped_superseded"] == 1
    assert estate.enqueued == [("sparsify", "only")]


@patch("api.services.storage.StorageService._sweep_act")
@patch("api.services.storage.Storage.pending_ids")
@patch("api.services.storage.Config")
def test_a_pass_digs_before_it_sparsifies(mock_config, mock_pending, mock_act):
    mock_config.get_storage_sweep_config.return_value = {
        "sparsify": True,
        "dig_holes": True,
    }
    mock_pending.return_value = ["x"]
    mock_act.return_value = {"selected": 0}
    StorageService.run_sweep_pass(ADMIN)
    calls = [(c.args[1], c.args[4]) for c in mock_act.call_args_list]
    assert calls == [("dig_holes", set()), ("sparsify", {"dig_holes"})]
    assert mock_pending.call_args_list[0].kwargs == {"status": "ready", "limit": 500}


@patch("api.services.storage.StorageService._sweep_act")
@patch("api.services.storage.Storage.zeros_due_ids")
@patch("api.services.storage.Config")
def test_a_pass_scans_the_disks_due_a_zero_scan(mock_config, mock_due, mock_act):
    mock_config.get_storage_sweep_config.return_value = {"zero_scan": True}
    mock_due.return_value = ["grown"]
    mock_act.return_value = {"selected": 1}
    out = StorageService.run_sweep_pass(ADMIN)
    mock_due.assert_called_once_with(500)
    assert mock_act.call_args.args[1:3] == ("zero_scan", ["grown"])
    assert out["actions"] == {"zero_scan": {"selected": 1}}


@patch("api.services.storage.StorageService._sweep_act")
@patch("api.services.storage.Storage.ready_ids_needing_check")
@patch("api.services.storage.Storage.pending_ids")
@patch("api.services.storage.Config")
def test_a_disk_marked_for_a_recheck_is_checked_first(
    mock_config, mock_pending, mock_age, mock_act
):
    mock_config.get_storage_sweep_config.return_value = {"check_integrity": True}
    mock_pending.return_value = ["dug", "old"]
    mock_age.return_value = ["old", "older"]
    mock_act.return_value = {}
    StorageService.run_sweep_pass(ADMIN)
    mock_pending.assert_called_once_with("check_integrity", status="ready", limit=500)
    assert mock_act.call_args.args[2] == ["dug", "old", "older"]


def test_the_enqueue_scans_zeros_on_the_maintenance_lane():
    storage = MagicMock()
    StorageService._sweep_enqueue("u1", "zero_scan", storage)
    storage.zero_scan.assert_called_once_with("u1", priority="low")


@patch("api.services.storage.Config")
def test_the_config_accepts_the_zero_scan_toggle(mock_config):
    mock_config.get_storage_sweep_config.return_value = {}
    StorageService.set_sweep_config(ADMIN, {"zero_scan": 1})
    mock_config.update_storage_sweep.assert_called_once_with({"zero_scan": True})


@patch("api.services.storage.get_storage")
def test_one_disk_can_be_scanned_on_demand(mock_get):
    mock_get.return_value.zero_scan.return_value = "t1"
    assert StorageService.zero_scan(ADMIN, "s1") == "t1"
    mock_get.return_value.zero_scan.assert_called_once_with("u-admin", priority="low")
