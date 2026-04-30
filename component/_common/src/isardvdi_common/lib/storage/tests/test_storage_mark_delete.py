#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StorageProcessed.mark_delete`` (tier 3.4 batch 1).

Migrated from the inline ``r.table("storage").get(...).update(...)``
block previously living in apiv4's
``services/admin/storage.py:delete_storage``. Pins the three branches
of the contract: row-missing → 404, replaced=0 → 500, success → no
exception.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on StorageProcessed so the method runs
    without a real rethinkdb."""
    from isardvdi_common.lib.storage import storage as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.StorageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.StorageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "StorageProcessed": mod.StorageProcessed}


class TestStorageProcessedMarkDelete:
    def test_not_found_when_row_missing(self, stub_rdb):
        """rdb returns ``skipped > 0`` → Error('not_found')."""
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.return_value = {
            "skipped": 1,
            "replaced": 0,
        }
        with pytest.raises(Error) as exc:
            stub_rdb["StorageProcessed"].mark_delete("missing-id")
        assert exc.value.error.get("error") == "not_found"
        assert exc.value.error.get("description_code") == "storage_not_found"

    def test_internal_server_when_replaced_zero(self, stub_rdb):
        """rdb returns ``replaced == 0`` (with no skipped) → 500."""
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.return_value = {
            "skipped": 0,
            "replaced": 0,
        }
        with pytest.raises(Error) as exc:
            stub_rdb["StorageProcessed"].mark_delete("stuck-id")
        assert exc.value.error.get("error") == "internal_server"

    def test_success_when_replaced(self, stub_rdb):
        """``replaced=1`` → no exception, returns None."""
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.return_value = {
            "skipped": 0,
            "replaced": 1,
        }
        assert stub_rdb["StorageProcessed"].mark_delete("ok-id") is None
