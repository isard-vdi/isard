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


def test_aggregate_carries_created_and_last_activity_dates():
    # both dates travel on the aggregate so the status endpoint and the socket
    # emit render the table's two date columns identically.
    m = SimpleNamespace(
        id="m", status="running", created_at=100.0, last_activity_at=250.0
    )
    p = mig.aggregate_status(m, [_item("r", "r", "template", "pending")])
    assert p["created_at"] == 100.0
    assert p["last_activity_at"] == 250.0


def test_aggregate_dates_absent_are_none():
    # a job created before last_activity_at existed carries None, never crashes.
    m = SimpleNamespace(id="m", status="planned")
    p = mig.aggregate_status(m, [_item("r", "r", "template", "pending")])
    assert p["created_at"] is None
    assert p["last_activity_at"] is None


def test_aggregate_status_can_omit_trees_for_the_socket():
    items = [
        _item("r", "r", "template", "released"),
        _item("d", "r", "desktop", "moving"),
    ]
    m = SimpleNamespace(id="m", status="running")
    full = mig.aggregate_status(m, items)  # default include_trees=True
    lean = mig.aggregate_status(m, items, include_trees=False)
    assert full["trees"] and lean["trees"] == []
    # totals are computed from items, not summed over trees, so they hold either way
    assert lean["totals"]["desktops"] == full["totals"]["desktops"] == 1
    assert lean["totals"]["items_total"] == 2


def test_aggregate_summary_is_job_row_only_and_carries_no_trees():
    # the socket summary is built from the persisted job row (fresh totals) with no
    # disks loaded and no per-tree list.
    m = SimpleNamespace(
        id="m",
        status="running",
        created_at=1.0,
        last_activity_at=2.0,
        config={"recurring": False},
        current_window={"open": True, "next_run_seconds": 5},
        totals={
            "items_total": 4400,
            "bytes_total": 100_000_000,
            "bytes_done": 0,
            "state_counts": {"pending": 4400},
        },
        throughput_ewma={"a:b": 50.0},
    )
    s = mig.aggregate_summary(m)
    assert "trees" not in s and "items" not in s
    assert s["totals"]["items_total"] == 4400
    assert s["state_counts"] == {"pending": 4400}
    assert s["status"] == "running"
    assert s["created_at"] == 1.0 and s["last_activity_at"] == 2.0
    assert s["eta_seconds"] == 2  # 100 MB / 50 MB/s
    assert s["next_run_seconds"] == 5


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
