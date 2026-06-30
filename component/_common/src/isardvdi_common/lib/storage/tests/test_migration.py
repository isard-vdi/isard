# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the storage-migration plan builder (pure layer).

The tree walk, item construction, classification, summary and the live
size-probe are tested here without a DB; the DB-driven ``build_plan_for_roots``
is exercised live against real storage rows in the P1 gate.
"""

import pytest
from isardvdi_common.lib.storage import migration as mig


# --------------------------------------------------------------------------- #
# walk_tree_topo — full recursion, parents-before-children
# --------------------------------------------------------------------------- #
def _children_map(mapping):
    return lambda nid: mapping.get(nid, [])


def test_walk_topo_full_recursion_three_levels():
    """derivatives is only 2-level; this walk MUST reach depth 3."""
    children = _children_map(
        {
            "root": ["a", "b"],
            "a": ["a1"],
            "a1": ["a1x"],  # great-grandchild — missed by Storage.derivatives
        }
    )
    order = mig.walk_tree_topo("root", children)
    assert order[0] == "root"
    assert set(order) == {"root", "a", "b", "a1", "a1x"}
    # parents strictly before children
    assert (
        order.index("root") < order.index("a") < order.index("a1") < order.index("a1x")
    )
    assert order.index("a") < order.index("a1")


def test_walk_topo_is_cycle_safe():
    children = _children_map({"a": ["b"], "b": ["a"]})  # cycle
    order = mig.walk_tree_topo("a", children)
    assert order == ["a", "b"]  # each visited once, terminates


def test_walk_topo_single_node():
    assert mig.walk_tree_topo("solo", _children_map({})) == ["solo"]


# --------------------------------------------------------------------------- #
# classify_kind
# --------------------------------------------------------------------------- #
def test_classify_kind():
    assert mig.classify_kind(has_children=True, perms=["r"]) == "template"
    assert mig.classify_kind(has_children=True, perms=["r", "w"]) == "template"
    assert mig.classify_kind(has_children=False, perms=["r", "w"]) == "desktop"
    assert mig.classify_kind(has_children=False, perms=["r"]) == "template"
    assert mig.classify_kind(has_children=False, perms=None) == "template"


# --------------------------------------------------------------------------- #
# build_tree_items
# --------------------------------------------------------------------------- #
def test_build_tree_items_topo_and_linkage():
    children = _children_map({"root": ["c"]})

    def node_info(nid):
        return {
            "root": {
                "kind": "template",
                "src_path": "/old/root.qcow2",
                "dst_path": "/new/root.qcow2",
                "dst_dir": "/new",
                "size_bytes": 100,
            },
            "c": {
                "kind": "desktop",
                "src_path": "/old/c.qcow2",
                "dst_path": "/new/c.qcow2",
                "dst_dir": "/new",
                "parent_storage_id": "root",
                "parent_dst_path": "/new/root.qcow2",
                "parent_dst_dir": "/new",
                "size_bytes": 50,
            },
        }[nid]

    items = mig.build_tree_items("mig1", "root", children, node_info)
    assert [it["storage_id"] for it in items] == ["root", "c"]
    # deterministic id == natural key (idempotent re-plan)
    assert [it["id"] for it in items] == ["mig1--root", "mig1--c"]
    assert [it["topo_index"] for it in items] == [0, 1]
    assert all(it["state"] == "pending" for it in items)
    assert all(it["tree_id"] == "root" for it in items)
    assert all(it["migration_id"] == "mig1" for it in items)
    child = items[1]
    assert child["parent_storage_id"] == "root"
    assert child["parent_dst_path"] == "/new/root.qcow2"
    assert child["size_bytes"] == 50
    assert items[0]["parent_storage_id"] is None  # root has no parent linkage


# --------------------------------------------------------------------------- #
# summarize_plan
# --------------------------------------------------------------------------- #
def test_summarize_plan_counts():
    items = [
        {"tree_id": "r", "storage_id": "r", "kind": "template", "size_bytes": 100},
        {"tree_id": "r", "storage_id": "t2", "kind": "template", "size_bytes": 10},
        {"tree_id": "r", "storage_id": "d1", "kind": "desktop", "size_bytes": 20},
        {"tree_id": "r", "storage_id": "d2", "kind": "desktop", "size_bytes": 30},
    ]
    s = mig.summarize_plan(items)
    assert s["trees"] == 1
    assert s["derivative_templates"] == 1  # t2 (template, not the root)
    assert s["desktops"] == 2
    assert s["items_total"] == 4
    assert s["bytes_total"] == 160
    assert s["bytes_done"] == 0
    assert s["state_counts"] == {"pending": 4}


def test_summarize_plan_multi_tree():
    items = [
        {"tree_id": "r1", "storage_id": "r1", "kind": "template", "size_bytes": 1},
        {"tree_id": "r2", "storage_id": "r2", "kind": "template", "size_bytes": 1},
        {"tree_id": "r2", "storage_id": "m", "kind": "media", "size_bytes": 5},
    ]
    s = mig.summarize_plan(items)
    assert s["trees"] == 2
    assert s["media"] == 1
    assert s["derivative_templates"] == 0


# --------------------------------------------------------------------------- #
# probe_actual_size
# --------------------------------------------------------------------------- #
def test_probe_actual_size_ok(monkeypatch):
    class _R:
        stdout = '{"actual-size": 4096, "virtual-size": 10485760}'

    monkeypatch.setattr(mig.subprocess, "run", lambda *a, **k: _R())
    assert mig.probe_actual_size("/x.qcow2") == 4096


def test_probe_actual_size_error_returns_none(monkeypatch):
    def boom(*a, **k):
        raise mig.subprocess.TimeoutExpired(cmd="qemu-img", timeout=30)

    monkeypatch.setattr(mig.subprocess, "run", boom)
    assert mig.probe_actual_size("/x.qcow2") is None


def test_probe_actual_size_missing_field_none(monkeypatch):
    class _R:
        stdout = '{"virtual-size": 10485760}'

    monkeypatch.setattr(mig.subprocess, "run", lambda *a, **k: _R())
    assert mig.probe_actual_size("/x.qcow2") is None
