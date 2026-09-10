# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the pure selection->roots core (DB-free).

A migration's "roots" are the topmost disks within the selected set: a disk is a
root when its backing parent is NOT itself in the set (parent is None, or the
parent lives outside the selection and therefore will not move). Walking each
root's full subtree then moves the whole backing chain consistently.
"""

from isardvdi_common.lib.storage import migration as mig


def _s(sid, parent=None, pool_id="p1", category="c1", directory_path="/isard/x"):
    return {
        "id": sid,
        "parent": parent,
        "pool_id": pool_id,
        "category": category,
        "directory_path": directory_path,
    }


# --------------------------------------------------------------------------- #
# explicit tree_ids always win and are de-duplicated / order-preserving
# --------------------------------------------------------------------------- #
def test_explicit_tree_ids_passthrough():
    storages = [_s("a"), _s("b"), _s("c")]
    roots = mig.compute_roots(storages, kind="pool", tree_ids=["b", "a", "b"])
    assert roots == ["b", "a"]


def test_explicit_tree_ids_filtered_to_existing():
    storages = [_s("a")]
    roots = mig.compute_roots(storages, kind="pool", tree_ids=["a", "ghost"])
    assert roots == ["a"]


# --------------------------------------------------------------------------- #
# pool selection: root == parent not in the pool
# --------------------------------------------------------------------------- #
def test_pool_root_is_topmost_in_pool():
    # tmpl(p1) <- desktop(p1): only tmpl is a root (desktop's parent is in pool)
    storages = [
        _s("tmpl", parent=None, pool_id="p1"),
        _s("desk", parent="tmpl", pool_id="p1"),
        _s("other", parent=None, pool_id="p2"),  # different pool, ignored
    ]
    roots = mig.compute_roots(storages, kind="pool", src_pool_id="p1")
    assert roots == ["tmpl"]


def test_pool_child_with_parent_outside_pool_is_a_root():
    # parent template lives in p2 (not selected); its desktop in p1 is a root
    # because the parent will not move -> the desktop only rebases-in-place...
    # but for the move-the-chain model it is the topmost IN the pool.
    storages = [
        _s("tmpl", parent=None, pool_id="p2"),
        _s("desk", parent="tmpl", pool_id="p1"),
    ]
    roots = mig.compute_roots(storages, kind="pool", src_pool_id="p1")
    assert roots == ["desk"]


def test_pool_standalone_disk_is_a_root():
    storages = [_s("solo", parent=None, pool_id="p1")]
    roots = mig.compute_roots(storages, kind="pool", src_pool_id="p1")
    assert roots == ["solo"]


def test_pool_deep_chain_only_top_is_root():
    storages = [
        _s("r", parent=None, pool_id="p1"),
        _s("c", parent="r", pool_id="p1"),
        _s("gc", parent="c", pool_id="p1"),
    ]
    roots = mig.compute_roots(storages, kind="pool", src_pool_id="p1")
    assert roots == ["r"]


# --------------------------------------------------------------------------- #
# category + path selections use the same root rule over a different member set
# --------------------------------------------------------------------------- #
def test_category_selection():
    storages = [
        _s("a", parent=None, category="c1"),
        _s("b", parent="a", category="c1"),
        _s("z", parent=None, category="c2"),
    ]
    roots = mig.compute_roots(storages, kind="category", category_id="c1")
    assert roots == ["a"]


def test_path_prefix_selection():
    storages = [
        _s("a", parent=None, directory_path="/isard/templates"),
        _s("b", parent="a", directory_path="/isard/templates"),
        _s("z", parent=None, directory_path="/other/templates"),
    ]
    roots = mig.compute_roots(storages, kind="path", path_prefix="/isard/")
    assert roots == ["a"]


def test_empty_selection_returns_no_roots():
    storages = [_s("a", pool_id="p2")]
    assert mig.compute_roots(storages, kind="pool", src_pool_id="p1") == []
