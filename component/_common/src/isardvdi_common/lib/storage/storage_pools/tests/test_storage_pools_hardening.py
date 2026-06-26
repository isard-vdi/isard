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
