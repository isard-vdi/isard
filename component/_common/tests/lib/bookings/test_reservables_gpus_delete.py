#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the DESTRUCTIVE path of ``ResourceItemsGpus`` in
``isardvdi_common.lib.bookings.reservables``: ``delete_reservable_vgpu``.

``delete_reservable_vgpu`` removes a whole vGPU reservable row from
``reservables_vgpus``. A deletion path that no test exercises is exactly the
kind that costs the most when it goes wrong, so these tests pin all three
branches:

* the row exists and the delete succeeds  -> row deleted + admin cache cleared,
* the row does not exist                   -> ``not_found`` (nothing deleted),
* the row exists but the delete does not report ``deleted`` -> ``internal_server``.

The real ``delete_reservable_vgpu`` is exercised (never mocked); only the rdb
connection surface, the admin-cache side effect and ``Helpers._check``'s input
are controlled.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def gpu_delete_stub(monkeypatch):
    from isardvdi_common.lib.bookings import reservables as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ResourceItemsGpus),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    # Spy on the admin-cache invalidation side effect (the only thing that
    # tells the Bookables listing the row is gone).
    clear_cache = MagicMock(name="clear_admin_table_list_cache")
    monkeypatch.setattr(mod.ApiAdmin, "clear_admin_table_list_cache", clear_cache)
    return {
        "mock_table": mock_table,
        "Cls": mod.ResourceItemsGpus,
        "clear_cache": clear_cache,
    }


def _reservables_get(stub):
    """The mock backing ``r.table("reservables_vgpus").get(subitem_id)``."""
    return stub["mock_table"].return_value.get.return_value


class TestDeleteReservableVgpu:
    def test_deletes_existing_and_clears_cache(self, gpu_delete_stub):
        get = _reservables_get(gpu_delete_stub)
        # Existence probe: row present.
        get.run.return_value = {"id": "NVIDIA-A40-1Q"}
        # The delete itself reports one row removed.
        get.delete.return_value.run.return_value = {
            "deleted": 1,
            "unchanged": 0,
            "errors": 0,
        }

        gpu_delete_stub["Cls"].delete_reservable_vgpu("NVIDIA-A40-1Q")

        # The reservable was actually deleted...
        get.delete.assert_called_once_with()
        gpu_delete_stub["mock_table"].assert_any_call("reservables_vgpus")
        # ...and the admin listing cache was invalidated so the row disappears.
        gpu_delete_stub["clear_cache"].assert_called_once_with("reservables_vgpus")

    def test_missing_row_raises_not_found_and_deletes_nothing(self, gpu_delete_stub):
        get = _reservables_get(gpu_delete_stub)
        # Existence probe: no such row.
        get.run.return_value = None

        with pytest.raises(Exception) as exc:
            gpu_delete_stub["Cls"].delete_reservable_vgpu("does-not-exist")

        assert getattr(exc.value, "status_code", None) == 404
        # Never attempt a delete on a row that isn't there...
        get.delete.assert_not_called()
        # ...and never touch the cache.
        gpu_delete_stub["clear_cache"].assert_not_called()

    def test_failed_delete_raises_internal_server(self, gpu_delete_stub):
        get = _reservables_get(gpu_delete_stub)
        # Row is present at probe time...
        get.run.return_value = {"id": "NVIDIA-A40-1Q"}
        # ...but the delete reports nothing removed and an error: Helpers._check
        # returns False -> internal_server.
        get.delete.return_value.run.return_value = {
            "deleted": 0,
            "unchanged": 0,
            "errors": 1,
        }

        with pytest.raises(Exception) as exc:
            gpu_delete_stub["Cls"].delete_reservable_vgpu("NVIDIA-A40-1Q")

        assert getattr(exc.value, "status_code", None) == 500
        # A failed delete must NOT report success to the admin listing.
        gpu_delete_stub["clear_cache"].assert_not_called()
