# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the cross-mode anti-overlap DECISION layer (pure).

INVARIANT: no two non-terminal jobs may reserve overlapping scope, detected
CROSS-MODE (a kind=pool job and a kind=path/category job touching the same disk
must be caught). Two reservation forms compose:

  * disk-level — the resolved storage-id closure (roots + subtrees); precise, and
    the concrete cross-mode signal for one-shot jobs;
  * descriptor-level — a content-INDEPENDENT (pool[, path]) claim, so a recurring
    "drain pool X" job keeps reserving X even between occurrences when X is empty
    and its ledger/closure is momentarily empty.

Overlap prefers OVER-rejecting to ever allowing a true overlap. The live wiring
(read ledgers, re-resolve scopes) is exercised in the service/E2E.
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


def _children_of(rows):
    by_parent = {}
    for s in rows:
        by_parent.setdefault(s.get("parent"), []).append(s["id"])
    return lambda nid: by_parent.get(nid, [])


# --------------------------------------------------------------------------- #
# resolved_ids_from_rows — the disk-id closure (roots + full subtrees)
# --------------------------------------------------------------------------- #
def test_closure_pool_includes_subtree():
    rows = [
        _s("tmpl", parent=None, pool_id="A"),
        _s("desk", parent="tmpl", pool_id="A"),
        _s("other", parent=None, pool_id="B"),
    ]
    ids = mig.resolved_ids_from_rows(
        rows, _children_of(rows), {"kind": "pool", "src_pool_id": "A"}
    )
    assert ids == {"tmpl", "desk"}


def test_closure_walks_children_outside_the_selected_set():
    # a desktop child living in pool B still MOVES because it descends from a
    # selected root in pool A -> the closure must include it (matches the planner)
    rows = [
        _s("tmpl", parent=None, pool_id="A"),
        _s("desk", parent="tmpl", pool_id="B"),
    ]
    ids = mig.resolved_ids_from_rows(
        rows, _children_of(rows), {"kind": "pool", "src_pool_id": "A"}
    )
    assert ids == {"tmpl", "desk"}


def test_closure_path_prefix():
    rows = [
        _s("a", directory_path="/isard/fast/t1"),
        _s("b", directory_path="/isard/slow/t2"),
    ]
    ids = mig.resolved_ids_from_rows(
        rows, _children_of(rows), {"kind": "path", "path_prefix": "/isard/fast"}
    )
    assert ids == {"a"}


# --------------------------------------------------------------------------- #
# scopes_overlap
# --------------------------------------------------------------------------- #
def test_scopes_overlap():
    assert mig.scopes_overlap({"a", "b"}, {"b", "c"}) is True
    assert mig.scopes_overlap({"a"}, {"b"}) is False
    assert mig.scopes_overlap(set(), {"a"}) is False


# --------------------------------------------------------------------------- #
# descriptor_claims — content-independent reservation
# --------------------------------------------------------------------------- #
def test_descriptor_pool_is_whole_pool():
    assert mig.descriptor_claims("pool", src_pool_id="A") == {("A", None)}


def test_descriptor_path_is_pool_plus_prefix():
    assert mig.descriptor_claims(
        "path", src_pool_id="A", path_prefix="/isard/fast"
    ) == {("A", "/isard/fast")}


def test_descriptor_category_is_assigned_pool_set():
    claims = mig.descriptor_claims("category", category_pools=["A", "B"])
    assert claims == {("A", None), ("B", None)}


# --------------------------------------------------------------------------- #
# descriptors_overlap — cross-mode, content-independent
# --------------------------------------------------------------------------- #
def test_descriptor_same_pool_overlaps():
    assert mig.descriptors_overlap({("A", None)}, {("A", None)}) is True


def test_descriptor_pool_vs_path_in_same_pool_overlaps():
    # whole-pool claim contains any path within it (pool vs path cross-mode)
    assert mig.descriptors_overlap({("A", None)}, {("A", "/isard/fast")}) is True


def test_descriptor_different_pools_disjoint():
    assert mig.descriptors_overlap({("A", None)}, {("B", None)}) is False
    assert mig.descriptors_overlap({("A", "/x")}, {("B", "/x")}) is False


def test_descriptor_path_prefix_containment():
    assert (
        mig.descriptors_overlap({("A", "/isard/fast")}, {("A", "/isard/fast/sub")})
        is True
    )
    assert (
        mig.descriptors_overlap({("A", "/isard/fast")}, {("A", "/isard/slow")}) is False
    )


def test_descriptor_category_vs_pool_via_assignment():
    # category C assigned to pools A,B; a pool job on A overlaps the category job
    cat_claims = mig.descriptor_claims("category", category_pools=["A", "B"])
    pool_claims = mig.descriptor_claims("pool", src_pool_id="A")
    assert mig.descriptors_overlap(cat_claims, pool_claims) is True
    # a pool job on an UNASSIGNED pool C does not
    assert (
        mig.descriptors_overlap(
            cat_claims, mig.descriptor_claims("pool", src_pool_id="C")
        )
        is False
    )


def test_descriptor_unknown_pool_over_rejects():
    # a path claim whose pool could not be resolved (None) is a wildcard: prefer
    # over-rejecting rather than silently allowing a possible overlap
    assert mig.descriptors_overlap({(None, "/isard/fast")}, {("A", None)}) is True


# --------------------------------------------------------------------------- #
# scope_conflict — the composed decision (disk-level + descriptor-level)
# --------------------------------------------------------------------------- #
def _job(jid, recurring=False, reserved_ids=frozenset(), claims=frozenset()):
    return {
        "id": jid,
        "recurring": recurring,
        "reserved_ids": set(reserved_ids),
        "claims": set(claims),
    }


def test_conflict_disk_level_one_shot():
    existing = [_job("m1", reserved_ids={"d1", "d2"})]
    assert mig.scope_conflict({"d2"}, {("A", None)}, False, existing) == "m1"
    assert mig.scope_conflict({"d9"}, {("Z", None)}, False, existing) is None


def test_conflict_empty_pool_recurring_reservation():
    # existing recurring "drain pool A" is fully drained: reserved_ids empty, but
    # its descriptor still reserves the whole pool -> a new pool-A job conflicts
    existing = [_job("rec", recurring=True, reserved_ids=set(), claims={("A", None)})]
    assert mig.scope_conflict(set(), {("A", None)}, False, existing) == "rec"
    # a job on a different pool is clear
    assert mig.scope_conflict({"x"}, {("B", None)}, False, existing) is None


def test_conflict_category_vs_pool_via_assignment_empty():
    # existing recurring category job (assigned pools A,B), currently empty; a new
    # pool-A job must be rejected via the descriptor even with no disks in flight
    existing = [
        _job(
            "cat", recurring=True, reserved_ids=set(), claims={("A", None), ("B", None)}
        )
    ]
    assert mig.scope_conflict(set(), {("A", None)}, False, existing) == "cat"


def test_conflict_new_recurring_vs_existing_oneshot_same_pool():
    # a NEW recurring pool-A job conflicts with an existing one-shot pool-A job
    # even if that one-shot's ledger disks are momentarily disjoint from the
    # (empty) new closure — the recurring reservation is descriptor-level
    existing = [_job("os", recurring=False, reserved_ids={"d1"}, claims={("A", None)})]
    assert mig.scope_conflict(set(), {("A", None)}, True, existing) == "os"


def test_conflict_two_oneshot_same_pool_disjoint_disks_allowed():
    # both one-shot on pool A but explicit disjoint tree_ids -> no descriptor
    # check (neither recurring), disk-level disjoint -> allowed
    existing = [
        _job("os", recurring=False, reserved_ids={"d1", "d2"}, claims={("A", None)})
    ]
    assert mig.scope_conflict({"d3"}, {("A", None)}, False, existing) is None


def test_conflict_skips_none_and_returns_first():
    existing = [
        _job("m1", reserved_ids={"z"}),
        _job("m2", reserved_ids={"d1"}),
    ]
    assert mig.scope_conflict({"d1"}, {("A", None)}, False, existing) == "m2"
