# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for aggregate_status — the shared admin-view payload (P2.6).

The apiv4 status endpoint and the change-handler socket emit both build the
aggregate from this one pure function, so they render identically.
"""

from types import SimpleNamespace

from isardvdi_common.lib.storage import migration as mig


def _item(sid, tree, kind, state, size=10):
    return {
        "id": f"m--{sid}",
        "storage_id": sid,
        "tree_id": tree,
        "topo_index": 0 if sid == tree else 1,
        "kind": kind,
        "state": state,
        "size_bytes": size,
        "dst_path": f"/dst/{sid}.qcow2",
        "error": None,
    }


def test_aggregate_totals_and_trees():
    items = [
        _item("r", "r", "template", "released"),
        _item("d1", "r", "desktop", "released"),
        _item("d2", "r", "desktop", "moving"),
    ]
    m = SimpleNamespace(id="mig-1", status="running")
    p = mig.aggregate_status(m, items)
    assert p["id"] == "mig-1" and p["status"] == "running"
    assert p["totals"]["items_total"] == 3
    assert p["totals"]["done"] == 2
    assert p["totals"]["bytes_total"] == 30
    assert p["totals"]["bytes_done"] == 20  # two released * 10
    assert p["totals"]["desktops"] == 2
    assert p["totals"]["state_counts"]["released"] == 2
    assert len(p["trees"]) == 1
    assert p["trees"][0]["done"] == 2


def test_aggregate_eta_uses_best_ewma_throughput():
    items = [_item("r", "r", "template", "pending", size=100_000_000)]  # 100 MB pending
    # 50 MB/s best of the EWMA samples -> 100MB/50MBps = 2s
    m = SimpleNamespace(
        id="m", status="running", throughput_ewma={"a:b": 10.0, "c:d": 50.0}
    )
    p = mig.aggregate_status(m, items)
    assert p["eta_seconds"] == 2


def test_aggregate_eta_none_without_samples():
    items = [_item("r", "r", "template", "pending")]
    m = SimpleNamespace(id="m", status="running")
    assert mig.aggregate_status(m, items)["eta_seconds"] is None


def test_aggregate_include_items_expands_per_disk():
    items = [
        _item("r", "r", "template", "released"),
        _item("d1", "r", "desktop", "moving"),
    ]
    m = SimpleNamespace(id="m", status="running")
    p = mig.aggregate_status(m, items, include_items=True)
    assert "items" not in mig.aggregate_status(m, items)  # off by default
    assert [i["storage_id"] for i in p["items"]] == ["r", "d1"]  # topo order
    assert p["items"][1]["state"] == "moving"


def test_aggregate_surfaces_config_and_window():
    m = SimpleNamespace(
        id="m",
        status="window_closed",
        config={"parallelism": 2, "bwlimit_kbs": 5000},
        current_window={"open": False, "remaining_seconds": 0},
    )
    p = mig.aggregate_status(m, [_item("r", "r", "template", "pending")])
    assert p["config"]["parallelism"] == 2
    assert p["current_window"]["open"] is False
