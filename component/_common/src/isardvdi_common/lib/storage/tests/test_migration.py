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
    assert s["items_by_kind"] == {"template": 2, "desktop": 2}
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


def test_summarize_plan_items_by_kind_reconciles_with_standalone_desktops():
    """A standalone desktop is its OWN tree root but is a desktop, not a template
    — so `trees` (3 here) must NOT be read as the template count. The per-kind
    counts are the only figures that sum back to items_total. Regression for the
    "3 templates + 8 desktops = 9 total" UI mismatch."""
    items = (
        # one real template tree: base template + 6 derived desktops
        [{"tree_id": "tpl", "storage_id": "tpl", "kind": "template", "size_bytes": 1}]
        + [
            {
                "tree_id": "tpl",
                "storage_id": f"d{i}",
                "kind": "desktop",
                "size_bytes": 1,
            }
            for i in range(6)
        ]
        # two standalone desktops, each its own tree root
        + [
            {
                "tree_id": f"s{i}",
                "storage_id": f"s{i}",
                "kind": "desktop",
                "size_bytes": 1,
            }
            for i in range(2)
        ]
    )
    s = mig.summarize_plan(items)
    assert s["trees"] == 3  # 1 template-rooted + 2 desktop-rooted
    assert s["items_total"] == 9
    assert s["items_by_kind"] == {"template": 1, "desktop": 8}
    # the invariant the UI relies on: per-kind counts sum to the total
    assert sum(s["items_by_kind"].values()) == s["items_total"]
    # and templates != trees (the exact bug: trees over-counted templates)
    assert s["items_by_kind"]["template"] != s["trees"]


# --------------------------------------------------------------------------- #
# build_plan_for_roots — destination path resolution (saga-0 regression)
#
# On a multi-path destination pool, get_usage_path() draws a weighted-random
# directory on EVERY call. The plan must resolve the usage directory ONCE per
# node and derive dst_path / dst_dir / the child's parent_dst_path from that one
# value — never three independent draws (which land the file in dir A, the DB
# directory_path in B and the child's rebase target in C → orphaned file +
# broken chain after the source delete).
# --------------------------------------------------------------------------- #
class _MultiPathPool:
    """Destination pool whose usage path differs on every draw (simulates a
    multi-path-per-usage pool where consecutive random.choices diverge)."""

    id = "dstpool"
    mountpoint = "/dst"

    def __init__(self):
        self._n = 0

    def get_usage_path(self, usage):
        self._n += 1
        return f"d{self._n}"  # d1, d2, d3, ... — a different dir each call


class _FakeStorage:
    """Minimal Storage stand-in driven by a class-level registry. Mirrors the
    REAL Storage: path_in_pool and get_storage_pool_path each call
    get_usage_path independently, so the legacy 3-draw plan diverges here."""

    registry: dict = {}

    @classmethod
    def exists(cls, sid):
        return sid in cls.registry

    def __init__(self, sid):
        self._sid = sid
        data = _FakeStorage.registry[sid]
        self.id = sid
        self.type = data["type"]
        self.parent = data["parent"]
        self.perms = data.get("perms", ["r"])
        self.pool_usage = data.get("pool_usage", "desktop")
        self._children_ids = data.get("children", [])

    @property
    def children(self):
        return [_FakeStorage(c) for c in self._children_ids]

    @property
    def path(self):
        return f"/src/{self.id}.{self.type}"

    def get_storage_pool_path(self, pool):
        if self.pool_usage is None:
            return None
        return f"{pool.mountpoint}/{pool.get_usage_path(self.pool_usage)}"

    def path_in_pool(self, pool):
        if self.pool_usage is None:
            return None
        return f"{pool.mountpoint}/{pool.get_usage_path(self.pool_usage)}/{self.id}.{self.type}"


class _FakeStorageProcessed:
    @staticmethod
    def get_storage_actual_size(sid):
        return 1000


def test_build_plan_resolves_dst_dir_once_per_node_multipath(monkeypatch):
    _FakeStorage.registry = {
        "root": {"type": "qcow2", "parent": None, "perms": ["r"], "children": ["c"]},
        "c": {"type": "qcow2", "parent": "root", "perms": ["r", "w"], "children": []},
    }
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )

    items, _ = mig.build_plan_for_roots("mig1", ["root"], _MultiPathPool())
    by_id = {it["storage_id"]: it for it in items}
    root, child = by_id["root"], by_id["c"]

    # 1. each node's file lives in its own recorded directory
    assert root["dst_path"] == f"{root['dst_dir']}/root.qcow2"
    assert child["dst_path"] == f"{child['dst_dir']}/c.qcow2"
    # 2. the child rebases onto exactly where the parent's file landed
    assert child["parent_dst_path"] == root["dst_path"]
    assert child["parent_dst_dir"] == root["dst_dir"]


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


def test_build_plan_survives_a_dangling_parent(monkeypatch):
    """``Storage.delete`` leaves the parent uuid behind on its children, so a
    live estate holds rows whose parent row is gone. Reaching one must not abort
    the whole plan: with no reachable backing parent the disk plans as a root,
    instead of raising not_found and taking every other tree down with it."""
    _FakeStorage.registry = {
        "orphan": {
            "type": "qcow2",
            "parent": "vanished",  # no such row
            "perms": ["r", "w"],
            "children": [],
        },
    }
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )

    items, totals = mig.build_plan_for_roots("m", ["orphan"], _MultiPathPool())

    assert len(items) == 1
    assert items[0]["storage_id"] == "orphan"
    assert not items[0].get("parent_storage_id")
    assert not items[0].get("parent_dst_path")


class _UsageLimitedPool:
    """Destination pool that serves ONLY the ``desktop`` usage — the shape seen
    in the field, where a pool has ``desktop: ['groups']`` and the other three
    usages present but with an EMPTY path list."""

    id = "dstpool"
    mountpoint = "/dst"

    def __init__(self):
        self.asked_usages = []

    def get_usage_path(self, usage):
        self.asked_usages.append(usage)
        if usage != "desktop":
            from isardvdi_common.helpers import error_factory

            raise error_factory.Error(
                "bad_request",
                f"Storage pool {self.id} has no '{usage}' path configured",
            )
        return "groups"


def test_build_plan_never_resolves_the_destination_of_a_parent_that_stays(monkeypatch):
    """A parent OUTSIDE the migrated set does not move, so its destination must
    never be resolved.

    ``compute_roots`` roots a tree precisely because its parent lives outside the
    selection, so this is the normal case: resolving that parent's destination
    asks the target pool for a path it does not serve and takes the whole plan
    down as a 500.
    """
    _FakeStorage.registry = {
        "tpl": {
            "type": "qcow2",
            "parent": None,
            "perms": ["r"],  # read-only base template, lives in another pool
            "pool_usage": "template",
            "children": ["d1", "d2", "d3"],
        },
        **{
            d: {
                "type": "qcow2",
                "parent": "tpl",
                "perms": ["r", "w"],
                "pool_usage": "desktop",
                "children": [],
            }
            for d in ("d1", "d2", "d3")
        },
    }
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )
    pool = _UsageLimitedPool()

    # the desktops are the roots: their parent is outside the selection
    items, totals = mig.build_plan_for_roots("m", ["d1", "d2", "d3"], pool)

    assert [it["storage_id"] for it in items] == ["d1", "d2", "d3"]
    assert totals["items_total"] == 3
    # the template's usage was never asked for — that ask IS the bug
    assert "template" not in pool.asked_usages
    for it in items:
        # the parent is still recorded (it is the disk's real backing owner)...
        assert it["parent_storage_id"] == "tpl"
        # ...but there is nothing to rebase onto: it stays exactly where it is,
        # so the disk's existing backing pointer still resolves.
        assert it["parent_dst_path"] is None
        assert it["parent_dst_dir"] is None


def test_build_plan_still_rebases_onto_a_parent_that_does_move(monkeypatch):
    """The other side of the same rule: a parent INSIDE the migrated set moves,
    so its child must still be rebased onto the parent's NEW path."""
    _FakeStorage.registry = {
        "root": {"type": "qcow2", "parent": None, "perms": ["r"], "children": ["c"]},
        "c": {"type": "qcow2", "parent": "root", "perms": ["r", "w"], "children": []},
    }
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )

    items, _ = mig.build_plan_for_roots("m", ["root"], _UsageLimitedPool())
    child = {it["storage_id"]: it for it in items}["c"]
    root = {it["storage_id"]: it for it in items}["root"]

    assert child["parent_storage_id"] == "root"
    assert child["parent_dst_path"] == root["dst_path"]
    assert child["parent_dst_dir"] == root["dst_dir"]


# item_kinds — move only some disk kinds, leave the rest of the chain in place
def _tpl_with_desktops():
    return {
        "tpl": {
            "type": "qcow2",
            "parent": None,
            "perms": ["r"],
            "pool_usage": "template",
            "children": ["d1", "d2", "d3"],
        },
        **{
            d: {
                "type": "qcow2",
                "parent": "tpl",
                "perms": ["r", "w"],
                "pool_usage": "desktop",
                "children": [],
            }
            for d in ("d1", "d2", "d3")
        },
    }


def _patch_storage(monkeypatch, registry):
    _FakeStorage.registry = registry
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )


def test_split_moving_subtrees_reroots_each_surviving_branch():
    """Dropping a node splits its tree into the sub-trees that survive, each
    rooted at its own topmost mover — so no ledger row ever claims a tree_id the
    ledger does not hold."""
    order = ["r", "a", "b", "a1", "b1"]
    parents = {"a": "r", "b": "r", "a1": "a", "b1": "b"}
    groups = dict(
        mig.split_moving_subtrees(
            order, lambda n: parents.get(n), lambda n: n != "r"  # the root stays
        )
    )
    assert groups == {"a": ["a", "a1"], "b": ["b", "b1"]}


def test_split_moving_subtrees_keeps_one_tree_when_the_root_moves():
    order = ["r", "a", "a1"]
    parents = {"a": "r", "a1": "a"}
    groups = dict(
        mig.split_moving_subtrees(order, lambda n: parents.get(n), lambda n: True)
    )
    assert groups == {"r": ["r", "a", "a1"]}


def test_item_kinds_empty_is_exactly_todays_plan(monkeypatch):
    """Backward compatibility is the contract: absent or empty must build the
    identical plan, item for item."""
    _patch_storage(monkeypatch, _tpl_with_desktops())
    baseline, totals_b = mig.build_plan_for_roots("m", ["tpl"], _MultiPathPool())

    _patch_storage(monkeypatch, _tpl_with_desktops())
    with_empty, totals_e = mig.build_plan_for_roots(
        "m", ["tpl"], _MultiPathPool(), item_kinds=[]
    )

    assert baseline == with_empty
    assert totals_b == totals_e
    assert totals_b["not_moving_total"] == 0


def test_item_kinds_desktop_moves_the_desktops_and_leaves_the_template(monkeypatch):
    """ "Move the desktops out of this pool, leave the base template where it is."

    The template is walked (the chain has to be understood) but does not move,
    so it gets no ledger row and — decisively — its destination is never
    resolved: this pool has no 'template' path at all, which is the shape that
    made the whole plan fail before kinds could be chosen.
    """
    _patch_storage(monkeypatch, _tpl_with_desktops())
    pool = _UsageLimitedPool()

    items, totals = mig.build_plan_for_roots("m", ["tpl"], pool, item_kinds=["desktop"])

    assert sorted(it["storage_id"] for it in items) == ["d1", "d2", "d3"]
    assert all(it["kind"] == "desktop" for it in items)
    assert "template" not in pool.asked_usages
    assert totals["items_total"] == 3
    assert totals["not_moving_by_kind"] == {"template": 1}
    assert totals["not_moving_total"] == 1
    for it in items:
        # each desktop is its own sub-tree root now: the template it backs onto
        # stays exactly where it is, so nothing rebases
        assert it["tree_id"] == it["storage_id"]
        assert it["topo_index"] == 0
        assert it["parent_storage_id"] == "tpl"
        assert it["parent_dst_path"] is None


def test_item_kinds_refuses_to_move_a_template_and_strand_its_desktops(monkeypatch):
    """The inverse selection would leave three desktops backing onto a path
    that no longer exists. Refuse, naming the pair and the way out — never
    build it silently."""
    _patch_storage(monkeypatch, _tpl_with_desktops())

    with pytest.raises(Exception) as raised:
        mig.build_plan_for_roots(
            "m", ["tpl"], _MultiPathPool(), item_kinds=["template"]
        )

    description = raised.value.error["description"]
    assert "tpl" in description
    assert "d1" in description or "d2" in description or "d3" in description
    assert (
        raised.value.error["description_code"]
        == "storage_migration_would_strand_derivative"
    )


def test_item_kinds_desktop_reaches_desktops_below_a_two_template_chain(monkeypatch):
    """The walk must keep going PAST the disks that stay, or the desktops under
    a derived template would never be found. Two templates deep, still only the
    desktops move — and the destination pool is never asked for the 'template'
    path it does not have."""
    _patch_storage(
        monkeypatch,
        {
            "base": {
                "type": "qcow2",
                "parent": None,
                "perms": ["r"],
                "pool_usage": "template",
                "children": ["mid"],
            },
            "mid": {
                "type": "qcow2",
                "parent": "base",
                "perms": ["r"],
                "pool_usage": "template",
                "children": ["d1", "d2"],
            },
            **{
                d: {
                    "type": "qcow2",
                    "parent": "mid",
                    "perms": ["r", "w"],
                    "pool_usage": "desktop",
                    "children": [],
                }
                for d in ("d1", "d2")
            },
        },
    )
    pool = _UsageLimitedPool()

    items, totals = mig.build_plan_for_roots(
        "m", ["base"], pool, item_kinds=["desktop"]
    )

    assert sorted(it["storage_id"] for it in items) == ["d1", "d2"]
    assert "template" not in pool.asked_usages
    assert totals["not_moving_by_kind"] == {"template": 2}
    for it in items:
        assert it["parent_storage_id"] == "mid"
        assert it["parent_dst_path"] is None  # 'mid' stays where it is


# order — which trees start first, and therefore which ones a budget reaches
def test_sort_tree_ids_none_preserves_the_callers_order():
    keys = {"c": 3, "a": 1, "b": 2}
    assert mig.sort_tree_ids(keys, None) == ["c", "a", "b"]
    assert mig.sort_tree_ids(keys, "none") == ["c", "a", "b"]


def test_sort_tree_ids_directions_are_exact_inverses():
    keys = {"cold": 100, "warm": 200, "hot": 300}
    oldest = mig.sort_tree_ids(keys, "oldest_first")
    newest = mig.sort_tree_ids(keys, "newest_first")
    assert oldest == ["cold", "warm", "hot"]
    assert newest == list(reversed(oldest))


def test_sort_tree_ids_ties_break_on_the_id_so_plan_and_run_agree():
    keys = {"zzz": 100, "aaa": 100}
    assert mig.sort_tree_ids(keys, "oldest_first") == ["aaa", "zzz"]
    # deterministic in both directions -- the summary and the execution must
    # walk the trees in exactly the same order or the preview is a lie
    assert mig.sort_tree_ids(keys, "newest_first") == ["zzz", "aaa"]


def test_sort_tree_ids_puts_trees_without_usage_data_last_in_both_directions():
    """No usage date is NOT evidence of being cold. Sorting those first would
    spend the whole budget on disks nobody can reason about."""
    keys = {"known_old": 100, "unknown": None, "known_new": 300}
    assert mig.sort_tree_ids(keys, "oldest_first") == [
        "known_old",
        "known_new",
        "unknown",
    ]
    assert mig.sort_tree_ids(keys, "newest_first") == [
        "known_new",
        "known_old",
        "unknown",
    ]


def test_tree_order_key_is_the_hottest_disk_that_moves():
    """max, not min: a tree holding one actively-used desktop is not cold just
    because it also holds a forgotten one."""
    accessed = {"cold": 100, "hot": 900}.get
    assert mig.tree_order_key(["cold", "hot"], lambda s: [], accessed) == 900


def test_tree_order_key_ignores_the_disks_that_stay():
    """A base template left behind as chain context carries a stale date that
    must not decide when the desktops under it move."""
    accessed = {"tpl": 100, "d1": 900}.get
    # only d1 moves; tpl is context and is not passed in
    assert mig.tree_order_key(["d1"], lambda s: [], accessed) == 900


def test_tree_order_key_of_a_mover_includes_its_derivatives(monkeypatch):
    """Deriving a desktop stamps the NEW desktop, never the template it came
    from, so a template's own date understates it by up to years. A mover is as
    hot as its hottest descendant, moving or not."""
    descendants = {"tpl": ["d1", "d2"]}
    accessed = {"tpl": 100, "d1": 500, "d2": 900}.get
    assert (
        mig.tree_order_key(["tpl"], lambda s: descendants.get(s, []), accessed) == 900
    )


def test_tree_order_key_is_none_when_nothing_that_moves_was_ever_used():
    assert mig.tree_order_key(["a", "b"], lambda s: [], {}.get) is None


def test_budget_prefix_is_what_the_runner_would_admit():
    sizes = {"a": 40, "b": 40, "c": 40}
    # a tree in flight always finishes, so the last admitted one may overshoot:
    # a+b spend 80 of 100, c is still admitted because the budget was not spent
    assert mig.budget_prefix(["a", "b", "c"], sizes.get, 100) == ["a", "b", "c"]
    assert mig.budget_prefix(["a", "b", "c"], sizes.get, 80) == ["a", "b"]
    assert mig.budget_prefix(["a", "b", "c"], sizes.get, 0) == ["a", "b", "c"]


def test_build_plan_without_an_order_stamps_no_key_and_asks_no_usage(monkeypatch):
    """Backward compatibility AND cost: the default path must not pay for the
    usage lookup a plan over a whole pool would make thousands of times."""
    _patch_storage(monkeypatch, _tpl_with_desktops())

    def _boom(*a, **k):
        raise AssertionError("the usage lookup ran without an order being asked for")

    monkeypatch.setattr(
        "isardvdi_common.models.domain.Domain.accessed_by_storage", _boom
    )

    items, totals = mig.build_plan_for_roots("m", ["tpl"], _MultiPathPool())

    assert all("tree_order_key" not in it for it in items)
    assert totals["order"] == "none"
    assert totals["order_trees_without_usage"] == 0


def test_build_plan_with_an_order_freezes_the_key_on_every_item(monkeypatch):
    _patch_storage(monkeypatch, _tpl_with_desktops())
    monkeypatch.setattr(
        "isardvdi_common.models.domain.Domain.accessed_by_storage",
        classmethod(lambda cls, ids: {"d1": 100, "d3": 900}),
    )

    items, totals = mig.build_plan_for_roots(
        "m", ["tpl"], _UsageLimitedPool(), item_kinds=["desktop"], order="oldest_first"
    )

    keys = {it["storage_id"]: it["tree_order_key"] for it in items}
    # each desktop is its own tree here, so each carries its own key -- and the
    # one nobody ever used carries None rather than a 0 that would sort first
    assert keys == {"d1": 100, "d2": None, "d3": 900}
    assert totals["order"] == "oldest_first"
    assert totals["order_trees_without_usage"] == 1
    assert mig.sort_tree_ids(keys, "oldest_first") == ["d1", "d3", "d2"]


def test_build_plan_refuses_a_disk_with_no_resolvable_destination(monkeypatch):
    """An unresolvable destination must fail the PLAN, not the disk at run time.

    ``get_storage_pool_path`` answers ``None`` -- rather than raising -- when the
    disk's usage cannot be reverse-mapped in the destination pool. That ``None``
    used to travel all the way into the item, and ``task.move`` then died inside
    ``os.path.isfile(None)`` with a TypeError the admin only ever saw as "move or
    rebase task failed", with the disk's whole subtree skipped behind it. Refuse
    up front, naming the disk, exactly as the raising sibling path already does.
    """
    _FakeStorage.registry = {
        "root": {
            "type": "qcow2",
            "parent": None,
            "perms": ["r"],
            "children": [],
            "pool_usage": None,
        },
    }
    monkeypatch.setattr("isardvdi_common.models.storage.Storage", _FakeStorage)
    monkeypatch.setattr(
        "isardvdi_common.lib.storage.storage.StorageProcessed", _FakeStorageProcessed
    )

    with pytest.raises(Exception) as raised:
        mig.build_plan_for_roots("mig1", ["root"], _MultiPathPool())

    message = str(raised.value)
    assert "root" in message, message
    assert "TypeError" not in message, message


# a failed disk must say WHY, not just that it failed
def test_task_error_line_is_the_exception_sentence():
    """The last line of a worker traceback carries the whole answer: which
    file, which destination, how much space was left and what the floor was."""
    exc = (
        "Traceback (most recent call last):\n"
        '  File "/opt/isardvdi/isardvdi_task/task.py", line 232, in _require_free_space\n'
        "    raise RuntimeError(\n"
        "RuntimeError: move: refusing to copy /pool/a/d1.qcow2: destination "
        "/pool/b would be left with 22157058048 bytes free, below the "
        "42949672960 byte floor (filesystem-level figure)\n"
    )
    line = mig.task_error_line(exc, "move/rebase task failed")
    assert line.startswith("RuntimeError: move: refusing to copy")
    assert "42949672960 byte floor" in line


def test_task_error_line_falls_back_when_there_is_no_traceback():
    assert mig.task_error_line("", "generic") == "generic"
    assert mig.task_error_line(None, "generic") == "generic"


def test_plan_tree_failure_reports_the_reason_it_was_given():
    items = [
        {
            "id": "i1",
            "storage_id": "d1",
            "tree_id": "d1",
            "topo_index": 0,
            "state": "moving",
            "parent_storage_id": None,
        },
    ]
    ((_it, state, reason),) = mig.plan_tree_failure(items, "d1", reason="no space left")
    assert state == "failed"
    assert reason == "no space left"
    # and without one, the historical wording is kept rather than an empty cell
    ((_it, _s, fallback),) = mig.plan_tree_failure(items, "d1")
    assert fallback == "move/rebase task failed"
