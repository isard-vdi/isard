#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the storage-pools multitenancy hardening ported from the
main layout's ``api/libv2/api_storage.py`` (MR !4631) into the apiv4
``StoragePoolsProcessed`` class.

Covers the pure validators (no DB):

* ``_check_mountpoint_safe`` — a category pool's mountpoint must stay under
  ``/isard/storage_pools/<single-safe-segment>`` (the only path bind-mounted
  into the storage and hypervisor containers).
* ``_check_paths_safe`` — per-usage path entries must be relative, with no
  ``..`` segment, leading ``/`` or null byte.

and the disjoint behaviour of the atomic
``remove_common_categories_from_other_pools`` (single server-side update,
``keep_pool_id`` filtering, empty no-op) using a stubbed rdb connection.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.storage.storage_pools import storage_pools as mod

SPP = mod.StoragePoolsProcessed


# --------------------------------------------------------------------------- #
# _check_paths_safe  (reject traversal / absolute / null byte in path entries)
# --------------------------------------------------------------------------- #
def test_check_paths_safe_accepts_relative_paths():
    SPP._check_paths_safe(
        {
            "desktop": [{"path": "desktops", "weight": 100}],
            "media": [{"path": "ssd/fast", "weight": 100}],
        }
    )  # no raise


@pytest.mark.parametrize(
    "bad_path",
    [
        "/absolute/path",
        "..",
        "../escape",
        "a/../b",
        "",
        "x\x00y",
    ],
)
def test_check_paths_safe_rejects_unsafe_paths(bad_path):
    with pytest.raises(Exception) as exc:
        SPP._check_paths_safe({"desktop": [{"path": bad_path, "weight": 100}]})
    assert exc.value.args[0] == "bad_request"


# --------------------------------------------------------------------------- #
# _check_paths_safe  ({category} placeholder: tier-before-category)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "good_path",
    [
        "fast/{category}/templates",
        "{category}/templates",
        "slow/{category}/desktops",
    ],
)
def test_check_paths_safe_accepts_category_token(good_path):
    SPP._check_paths_safe(
        {"template": [{"path": good_path, "weight": 100}]}
    )  # no raise


@pytest.mark.parametrize(
    "bad_path",
    [
        "fast/{category}/{category}/x",  # token more than once
        "fast/x{category}y/templates",  # token not a full segment
        "fast/{cat}/templates",  # unknown placeholder
        "fast/{category/templates",  # stray opening brace
        "fast/category}/templates",  # stray closing brace
    ],
)
def test_check_paths_safe_rejects_bad_token(bad_path):
    with pytest.raises(Exception) as exc:
        SPP._check_paths_safe({"template": [{"path": bad_path, "weight": 100}]})
    assert exc.value.args[0] == "bad_request"


# --------------------------------------------------------------------------- #
# _check_mountpoint_safe  (pool mountpoint must stay under /isard/storage_pools)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "mountpoint",
    [
        "/isard/storage_pools/fast-nvme",
        "/isard/storage_pools/pool1",
        "/isard/storage_pools/a.b_c-1",
    ],
)
def test_check_mountpoint_safe_accepts_named_leaf(mountpoint):
    SPP._check_mountpoint_safe(mountpoint)  # no raise


@pytest.mark.parametrize(
    "mountpoint",
    [
        "/mnt/fast",  # external path - not mounted into the containers
        "/isard",  # reserved for the default pool
        "/isard/groups",  # not under storage_pools
        "/isard/storage_pools/",  # empty leaf
        "/isard/storage_pools/a/b",  # more than one segment
        "/isard/storage_pools/../etc",  # traversal
        "/etc/passwd",
        "",
    ],
)
def test_check_mountpoint_safe_rejects_outside_or_unsafe(mountpoint):
    with pytest.raises(Exception) as exc:
        SPP._check_mountpoint_safe(mountpoint)
    assert exc.value.args[0] == "bad_request"


# --------------------------------------------------------------------------- #
# remove_common_categories_from_other_pools  (atomic reassignment)
# --------------------------------------------------------------------------- #
@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on StoragePoolsProcessed so the method runs
    without a real rethinkdb. Mirrors lib/storage/tests/test_storage_get_row.py."""

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(SPP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(SPP),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    return mock_table


def test_remove_common_categories_single_atomic_update(stub_rdb):
    SPP.remove_common_categories_from_other_pools(["cat-a"])
    # Single server-side update over the table; no pluck-then-loop.
    assert stub_rdb.return_value.update.called
    assert not stub_rdb.return_value.pluck.called


def test_remove_common_categories_keep_pool_filters(stub_rdb):
    SPP.remove_common_categories_from_other_pools(["cat-a"], keep_pool_id="pool-b")
    # The pool being written is skipped via a server-side filter before update.
    assert stub_rdb.return_value.filter.called
    assert stub_rdb.return_value.filter.return_value.update.called


def test_remove_common_categories_empty_is_noop(stub_rdb):
    SPP.remove_common_categories_from_other_pools([])
    assert not stub_rdb.called


# --------------------------------------------------------------------------- #
# _check_mountpoint_unique  (a mountpoint is a pool's on-disk identity; two
# pools sharing one make path->pool resolution ambiguous and silently mis-route
# download tasks to a worker-less queue, so creation/rename must reject it)
# --------------------------------------------------------------------------- #
def test_check_mountpoint_unique_rejects_duplicate(stub_rdb):
    # Another pool already owns this mountpoint -> count() > 0 -> reject.
    stub_rdb.return_value.filter.return_value.count.return_value.run.return_value = 1
    with pytest.raises(Exception) as exc:
        SPP._check_mountpoint_unique("/isard/storage_pools/dup")
    assert exc.value.args[0] == "bad_request"


def test_check_mountpoint_unique_accepts_free_mountpoint(stub_rdb):
    # No other pool uses it -> count() == 0 -> no raise.
    stub_rdb.return_value.filter.return_value.count.return_value.run.return_value = 0
    SPP._check_mountpoint_unique("/isard/storage_pools/free")  # no raise


def test_check_mountpoint_unique_excludes_self_on_rename(stub_rdb):
    # On update the pool keeping its own mountpoint must not clash with itself:
    # a second server-side filter drops its own row before counting.
    stub_rdb.return_value.filter.return_value.filter.return_value.count.return_value.run.return_value = (
        0
    )
    SPP._check_mountpoint_unique(
        "/isard/storage_pools/x", exclude_id="self"
    )  # no raise
    assert stub_rdb.return_value.filter.return_value.filter.called


# --------------------------------------------------------------------------- #
# default-pool path validation
# --------------------------------------------------------------------------- #
def test_check_mountpoint_safe_rejects_reserved_default_leaf():
    # /isard/storage_pools/default is reserved for the default pool.
    with pytest.raises(Exception) as exc:
        SPP._check_mountpoint_safe("/isard/storage_pools/default")
    assert exc.value.args[0] == "bad_request"


def _default_paths(desktop):
    return {
        "desktop": [{"path": desktop, "weight": 100}],
        "media": [{"path": "media", "weight": 100}],
        "template": [{"path": "templates", "weight": 100}],
        "volatile": [{"path": "volatile", "weight": 100}],
    }


def test_check_default_paths_accepts_legacy_groups():
    SPP._check_default_paths(_default_paths("groups"))  # no raise


def test_check_default_paths_accepts_new_desktops():
    SPP._check_default_paths(_default_paths("desktops"))  # no raise


def test_check_default_paths_requires_every_usage_type():
    bad = _default_paths("desktops")
    bad["volatile"] = []
    with pytest.raises(Exception) as exc:
        SPP._check_default_paths(bad)
    assert exc.value.args[0] == "bad_request"


# --------------------------------------------------------------------------- #
# update_storage_pool — default pool protected fields (bug #2370)
#
# The default pool's name/description/mountpoint/category-set are immutable.
# Previously an attempt to change them was silently ``data.pop``-ed, so the API
# answered 204/OK while the rename was discarded (a client can never tell its
# edit was dropped). It must instead be rejected explicitly (like ``enabled``),
# while a no-op resend of the current value (as a full-object PUT sends) is
# tolerated and the non-protected fields still apply.
# --------------------------------------------------------------------------- #
DEFAULT_ID = mod.DEFAULT_STORAGE_POOL_ID


@pytest.fixture
def stub_default_pool(monkeypatch):
    """StoragePool.get(<default id>) returns a fixed current row so
    update_storage_pool can diff protected fields against it."""
    current = {
        "id": DEFAULT_ID,
        "name": "isard",
        "description": "Default storage pool",
        "mountpoint": "/isard",
        "categories": ["cat-a", "cat-b"],
        "enabled": True,
    }
    monkeypatch.setattr(mod.StoragePool, "get", lambda _id: dict(current))
    return current


def _default_update_mock(stub_rdb):
    """The r.table('storage_pool').get(id).update(data) mock."""
    return stub_rdb.return_value.get.return_value.update


def test_update_default_pool_rejects_rename(stub_default_pool, stub_rdb):
    with pytest.raises(Exception) as exc:
        SPP.update_storage_pool(DEFAULT_ID, {"name": "renamed"})
    assert exc.value.args[0] == "bad_request"
    assert "name" in exc.value.args[1]
    # The bug: it must NOT silently reach the DB write.
    assert not _default_update_mock(stub_rdb).called


def test_update_default_pool_rejects_description_change(stub_default_pool, stub_rdb):
    with pytest.raises(Exception) as exc:
        SPP.update_storage_pool(DEFAULT_ID, {"description": "new desc"})
    assert exc.value.args[0] == "bad_request"
    assert "description" in exc.value.args[1]
    assert not _default_update_mock(stub_rdb).called


def test_update_default_pool_tolerates_noop_resend(stub_default_pool, stub_rdb):
    # A full-object PUT resends the current name unchanged alongside a real edit.
    SPP.update_storage_pool(DEFAULT_ID, {"name": "isard", "write": True})
    update = _default_update_mock(stub_rdb)
    assert update.called
    payload = update.call_args.args[0]
    assert "name" not in payload  # popped as a no-op, not written
    assert payload.get("write") is True  # the real edit is applied


def test_update_default_pool_allows_non_protected_field(stub_default_pool, stub_rdb):
    SPP.update_storage_pool(DEFAULT_ID, {"write": True})
    update = _default_update_mock(stub_rdb)
    assert update.called
    assert update.call_args.args[0].get("write") is True


def test_update_default_pool_categories_reorder_is_noop(stub_default_pool, stub_rdb):
    # Same set, different order → tolerated (compared as a set), reaches the DB.
    SPP.update_storage_pool(
        DEFAULT_ID, {"categories": ["cat-b", "cat-a"], "write": True}
    )
    assert _default_update_mock(stub_rdb).called
