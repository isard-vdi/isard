# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for isardvdi_common.models.storage_pool.StoragePool.

These tests construct StoragePool instances with ``__new__`` so they never
touch RethinkDB or socketio (the custom ``__init__``/``__setattr__`` hit the
DB on every access). Class methods that query the DB are driven by
monkeypatching the module-level ``r`` and the connection context.

apiv4 layout note: ``get_by_user_kind`` returns ``cls.init_document(**sp)``
(which would INSERT into RethinkDB and re-fetch), so the ``patched_kind``
fixture monkeypatches ``init_document`` to build a bare pool from the kwargs.
``get_by_path`` returns ``cls(best["id"])`` so ``patched_path`` monkeypatches
``__init__`` instead — mirroring the harness style of the sibling
``test_storage_chain_definitions.py``.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.models import storage_pool as sp_mod
from isardvdi_common.models.storage_pool import StoragePool


def make_pool(**attrs):
    """Build a StoragePool without running its DB/socketio __init__."""
    pool = StoragePool.__new__(StoragePool)
    for key, value in attrs.items():
        object.__setattr__(pool, key, value)
    return pool


# --------------------------------------------------------------------------- #
# get_usage_path  (F1)
# --------------------------------------------------------------------------- #
def test_get_usage_path_single_path():
    pool = make_pool(id="p", paths={"desktop": [{"path": "ssd", "weight": 100}]})
    assert pool.get_usage_path("desktop") == "ssd"


def test_get_usage_path_weighted_returns_configured_path():
    pool = make_pool(
        id="p",
        paths={
            "desktop": [
                {"path": "ssd", "weight": 70},
                {"path": "hdd", "weight": 30},
            ]
        },
    )
    # Whatever the weighted draw, it must be one of the configured paths.
    assert pool.get_usage_path("desktop") in {"ssd", "hdd"}


def test_get_usage_path_empty_list_raises():
    """A configured-but-empty usage list must not IndexError (F1)."""
    pool = make_pool(id="p", paths={"template": []})
    with pytest.raises(Exception) as exc:
        pool.get_usage_path("template")
    assert exc.value.args[0] == "bad_request"


def test_get_usage_path_missing_usage_raises():
    """A usage with no key at all must raise the same clear error (F1)."""
    pool = make_pool(id="p", paths={"desktop": [{"path": "g", "weight": 100}]})
    with pytest.raises(Exception) as exc:
        pool.get_usage_path("media")
    assert exc.value.args[0] == "bad_request"


# --------------------------------------------------------------------------- #
# get_by_user_kind  (F1 empty-path skip, F5 disabled skip)
# --------------------------------------------------------------------------- #
class _NoopCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def patched_kind(monkeypatch):
    """Drive get_by_user_kind without a real DB.

    Returns a helper that, given the user's category and the list of pool
    rows, wires the module so get_by_user_kind resolves against them.
    """
    monkeypatch.setattr(
        StoragePool, "_rdb_context", classmethod(lambda cls: _NoopCtx())
    )
    monkeypatch.setattr(
        type(StoragePool),
        "_rdb_connection",
        property(lambda cls: MagicMock(name="conn")),
        raising=False,
    )

    # apiv4's get_by_user_kind returns ``cls.init_document(**sp)`` which would
    # INSERT into RethinkDB and re-fetch. Replace it with a bare-pool builder
    # so the selection logic can be asserted without a DB.
    def fake_init_document(cls, *args, **kw):
        pool = cls.__new__(cls)
        if args:
            object.__setattr__(pool, "id", args[0])
        for k, v in kw.items():
            object.__setattr__(pool, k, v)
        return pool

    monkeypatch.setattr(StoragePool, "init_document", classmethod(fake_init_document))

    def _setup(category_id, pools):
        def fake_table(name):
            table = MagicMock(name=f"table:{name}")
            if name == "users":
                table.get.return_value.__getitem__.return_value.run.return_value = (
                    category_id
                )
            else:  # storage_pool
                table.run.return_value = pools
            return table

        fake_r = MagicMock(name="r")
        fake_r.table.side_effect = fake_table
        monkeypatch.setattr(sp_mod, "r", fake_r)

    return _setup


def _default_pool():
    return {
        "id": DEFAULT_STORAGE_POOL_ID,
        "categories": [],
        "enabled": True,
        "paths": {
            "desktop": [{"path": "groups", "weight": 100}],
            "media": [{"path": "media", "weight": 100}],
            "template": [{"path": "templates", "weight": 100}],
            "volatile": [{"path": "volatile", "weight": 100}],
        },
    }


def test_get_by_user_kind_selects_matching_pool(patched_kind):
    pool = {
        "id": "pool-a",
        "categories": ["cat-a"],
        "enabled": True,
        "paths": {"desktop": [{"path": "ssd", "weight": 100}]},
    }
    patched_kind("cat-a", [_default_pool(), pool])
    result = StoragePool.get_by_user_kind("user-1", "desktop")
    assert result.id == "pool-a"


def test_get_by_user_kind_skips_empty_path_type(patched_kind):
    """Category pool that lists template:[] must fall back to default (F1)."""
    pool = {
        "id": "pool-a",
        "categories": ["cat-a"],
        "enabled": True,
        "paths": {
            "desktop": [{"path": "ssd", "weight": 100}],
            "template": [],
        },
    }
    patched_kind("cat-a", [_default_pool(), pool])
    result = StoragePool.get_by_user_kind("user-1", "template")
    assert result.id == DEFAULT_STORAGE_POOL_ID


def test_get_by_user_kind_skips_disabled_pool(patched_kind):
    """Disabled category pool must not be selected (F5)."""
    pool = {
        "id": "pool-a",
        "categories": ["cat-a"],
        "enabled": False,
        "paths": {"desktop": [{"path": "ssd", "weight": 100}]},
    }
    patched_kind("cat-a", [_default_pool(), pool])
    result = StoragePool.get_by_user_kind("user-1", "desktop")
    assert result.id == DEFAULT_STORAGE_POOL_ID


def test_get_by_user_kind_unassigned_category_uses_default(patched_kind):
    pool = {
        "id": "pool-a",
        "categories": ["cat-a"],
        "enabled": True,
        "paths": {"desktop": [{"path": "ssd", "weight": 100}]},
    }
    patched_kind("cat-other", [_default_pool(), pool])
    result = StoragePool.get_by_user_kind("user-1", "desktop")
    assert result.id == DEFAULT_STORAGE_POOL_ID


# --------------------------------------------------------------------------- #
# get_by_path  (F2 longest-prefix resolution, F3 default fallback)
# --------------------------------------------------------------------------- #
CAT_POOL_MP = "/isard/storage_pools/pool-a"


@pytest.fixture
def patched_path(monkeypatch):
    """Drive get_by_path against an in-memory list of {id, mountpoint} rows."""
    monkeypatch.setattr(
        StoragePool, "_rdb_context", classmethod(lambda cls: _NoopCtx())
    )
    monkeypatch.setattr(
        type(StoragePool),
        "_rdb_connection",
        property(lambda cls: MagicMock(name="conn")),
        raising=False,
    )

    def fake_init(self, *args, **kw):
        if args:
            object.__setattr__(self, "id", args[0])
        for k, v in kw.items():
            object.__setattr__(self, k, v)

    monkeypatch.setattr(StoragePool, "__init__", fake_init)

    def _setup(pools):
        table = MagicMock(name="table")
        table.pluck.return_value.run.return_value = pools
        fake_r = MagicMock(name="r")
        fake_r.table.return_value = table
        monkeypatch.setattr(sp_mod, "r", fake_r)

    return _setup


def test_get_by_path_resolves_category_pool(patched_path):
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-a", "mountpoint": CAT_POOL_MP},
        ]
    )
    result = StoragePool.get_by_path(CAT_POOL_MP + "/cat/desktops/x.qcow2")
    assert [p.id for p in result] == ["pool-a"]


def test_get_by_path_default_for_default_path(patched_path):
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-a", "mountpoint": CAT_POOL_MP},
        ]
    )
    result = StoragePool.get_by_path("/isard/groups/x.qcow2")
    assert [p.id for p in result] == [DEFAULT_STORAGE_POOL_ID]


def test_get_by_path_named_leaf_resolves(patched_path):
    """A pool's admin-chosen leaf name under /isard/storage_pools resolves to
    that pool (not the default ancestor), whatever the leaf is called."""
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-fast", "mountpoint": "/isard/storage_pools/fast-nvme"},
        ]
    )
    result = StoragePool.get_by_path(
        "/isard/storage_pools/fast-nvme/cat/desktops/x.qcow2"
    )
    assert [p.id for p in result] == ["pool-fast"]


def test_get_by_path_longest_prefix_wins(patched_path):
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-a", "mountpoint": CAT_POOL_MP},
        ]
    )
    # "/isard" is also a prefix but the category mountpoint is longer.
    result = StoragePool.get_by_path(CAT_POOL_MP + "/cat/media/y.qcow2")
    assert [p.id for p in result] == ["pool-a"]


def test_get_by_path_no_prefix_match_uses_default(patched_path):
    """Robustness: a path under no known mountpoint (e.g. a removed pool or a
    stale/legacy record) falls back to default, never an empty list."""
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-a", "mountpoint": CAT_POOL_MP},
        ]
    )
    result = StoragePool.get_by_path("/srv/other/x.qcow2")
    assert [p.id for p in result] == [DEFAULT_STORAGE_POOL_ID]


def test_get_by_path_sibling_prefix_not_matched(patched_path):
    """'/isard' must not match '/isardvdi/...'."""
    patched_path(
        [
            {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard"},
            {"id": "pool-v", "mountpoint": "/isardvdi"},
        ]
    )
    result = StoragePool.get_by_path("/isardvdi/groups/x.qcow2")
    assert [p.id for p in result] == ["pool-v"]


# --------------------------------------------------------------------------- #
# get_usage_by_path  (F9 directory + file-path tolerance, mountpoint-agnostic)
# --------------------------------------------------------------------------- #
def _category_pool(mountpoint="/isard/storage_pools/pool-a", id="pool-a"):
    return make_pool(
        id=id,
        mountpoint=mountpoint,
        paths={
            "desktop": [{"path": "desktops", "weight": 100}],
            "template": [{"path": "templates", "weight": 100}],
        },
    )


def _default_pool_obj():
    return make_pool(
        id=DEFAULT_STORAGE_POOL_ID,
        mountpoint="/isard",
        paths={
            "desktop": [{"path": "groups", "weight": 100}],
            "template": [{"path": "templates", "weight": 100}],
        },
    )


def test_get_usage_by_path_category_directory():
    pool = _category_pool()
    assert pool.get_usage_by_path(pool.mountpoint + "/cat/desktops") == "desktop"


def test_get_usage_by_path_category_file_path():
    """F9: a full file path (with <id>.qcow2) must resolve, not return None."""
    pool = _category_pool()
    assert (
        pool.get_usage_by_path(pool.mountpoint + "/cat/desktops/abc.qcow2") == "desktop"
    )


def test_get_usage_by_path_default_directory():
    pool = _default_pool_obj()
    assert pool.get_usage_by_path("/isard/groups") == "desktop"


def test_get_usage_by_path_default_file_path():
    pool = _default_pool_obj()
    assert pool.get_usage_by_path("/isard/groups/abc.qcow2") == "desktop"


def test_get_usage_by_path_named_leaf_mountpoint():
    """Category stripping keys off the pool id, so it works for any pool leaf
    name under /isard/storage_pools, not just an id-shaped one."""
    pool = make_pool(
        id="pool-fast",
        mountpoint="/isard/storage_pools/fast-nvme",
        paths={"desktop": [{"path": "d", "weight": 100}]},
    )
    assert (
        pool.get_usage_by_path("/isard/storage_pools/fast-nvme/cat/d/abc.qcow2")
        == "desktop"
    )


def test_get_usage_by_path_outside_mountpoint_is_none():
    pool = _category_pool()
    assert pool.get_usage_by_path("/somewhere/else/x.qcow2") is None


def test_get_usage_by_path_unknown_usage_is_none():
    pool = _category_pool()
    assert pool.get_usage_by_path(pool.mountpoint + "/cat/unknowndir/x.qcow2") is None
