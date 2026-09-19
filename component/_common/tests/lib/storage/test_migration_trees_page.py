# SPDX-License-Identifier: AGPL-3.0-or-later

"""tree_summaries_page: server-side paginated / filterable per-tree summaries.

The list view no longer ships every tree; a job's expand pulls one page at a time,
filterable by aggregated state and by a text match on the tree id or a disk path.
"""

from isardvdi_common.lib.storage import migration as mig


def _lr(sid, tree, state="pending", kind="desktop", size=10, src=None, dst=None):
    return {
        "id": "m--" + sid,
        "storage_id": sid,
        "tree_id": tree,
        "topo_index": 0 if sid == tree else 1,
        "kind": kind,
        "state": state,
        "size_bytes": size,
        "src_path": src or f"/src/{sid}.qcow2",
        "dst_path": dst or f"/dst/{sid}.qcow2",
        "tree_order_key": None,
    }


def _rows(n):
    # n singleton trees t0..t(n-1), all pending
    return [_lr(f"t{i}", f"t{i}") for i in range(n)]


def test_pagination_cuts_the_page_and_reports_total():
    rows = _rows(5)
    p1 = mig.tree_summaries_page(rows, page=1, per_page=2)
    assert p1["total"] == 5 and p1["page"] == 1 and p1["per_page"] == 2
    assert [t["tree_id"] for t in p1["trees"]] == ["t0", "t1"]
    p3 = mig.tree_summaries_page(rows, page=3, per_page=2)
    assert [t["tree_id"] for t in p3["trees"]] == ["t4"]  # last, partial page


def test_state_filter_keeps_only_trees_with_a_disk_in_that_state():
    rows = _rows(3) + [_lr("m", "m", state="moving")]
    page = mig.tree_summaries_page(rows, per_page=50, state="moving")
    assert [t["tree_id"] for t in page["trees"]] == ["m"]
    assert page["total"] == 1
    # a state no tree is in -> empty
    assert mig.tree_summaries_page(rows, state="released")["total"] == 0


def test_q_matches_tree_id_or_a_disk_path():
    rows = [
        _lr("aaa", "aaa", dst="/dst/aaa.qcow2"),
        _lr("bbb", "bbb", dst="/pool-x/bbb.qcow2"),
    ]
    assert [t["tree_id"] for t in mig.tree_summaries_page(rows, q="aaa")["trees"]] == [
        "aaa"
    ]
    # match on the destination path, case-insensitive
    assert [
        t["tree_id"] for t in mig.tree_summaries_page(rows, q="POOL-X")["trees"]
    ] == ["bbb"]


def test_tree_summary_counts_kinds_and_states():
    tit = [
        _lr("r", "r", state="released", kind="template"),
        _lr("c", "r", state="moving", kind="template"),
        _lr("d", "r", state="pending", kind="desktop"),
    ]
    s = mig.tree_summary("r", tit)
    assert s["items_total"] == 3
    assert s["derivative_templates"] == 1  # template with storage_id != tree_id
    assert s["desktops"] == 1
    assert s["completed"] == 1  # one released
    assert s["state_counts"] == {"released": 1, "moving": 1, "pending": 1}
