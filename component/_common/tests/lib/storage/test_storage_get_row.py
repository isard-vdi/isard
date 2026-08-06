#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StorageProcessed.get_storage_row`` and
``StorageProcessed.batch_stop_desktops_by_kind_ids`` (tier 3.4 batch 3).

Migrated from inline rethink queries previously living in apiv4's
``services/storage.py``. ``get_storage_row`` pins the raw-row read
that bypasses the ``Storage`` model wrapper;
``batch_stop_desktops_by_kind_ids`` pins the chunked update used by
the storage-action stop-desktops path.
"""

from unittest.mock import MagicMock, call

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on StorageProcessed so the methods run
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


class TestGetStorageRow:
    def test_returns_row_when_present(self, stub_rdb):
        row = {"id": "s1", "status": "ready", "user_id": "u-1"}
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = row
        result = stub_rdb["StorageProcessed"].get_storage_row("s1")
        assert result == row
        stub_rdb["mock_table"].assert_any_call("storage")
        stub_rdb["mock_table"].return_value.get.assert_called_with("s1")

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["StorageProcessed"].get_storage_row("missing-id") is None


class TestBatchStopDesktopsByKindIds:
    def test_single_batch_dispatches_one_update(self, stub_rdb):
        update_data = {"status": "Stopping", "accessed": 1700000000}
        stub_rdb["StorageProcessed"].batch_stop_desktops_by_kind_ids(
            desktop_ids=["d1", "d2", "d3"],
            update_data=update_data,
            current_status="Started",
            batch_size=10,
        )
        # One get_all call (batch fits in one chunk).
        get_all = stub_rdb["mock_table"].return_value.get_all
        assert get_all.call_count == 1
        # Keys are kind-pairs.
        args, kwargs = get_all.call_args
        assert kwargs == {"index": "kind_ids"}
        assert list(args) == [
            ["desktop", "d1"],
            ["desktop", "d2"],
            ["desktop", "d3"],
        ]
        # Status filter on the chain.
        get_all.return_value.filter.assert_called_with({"status": "Started"})
        get_all.return_value.filter.return_value.update.assert_called_with(update_data)

    def test_chunks_when_over_batch_size(self, stub_rdb):
        # 5 ids with batch_size=2 → 3 chunks (2, 2, 1).
        ids = ["d1", "d2", "d3", "d4", "d5"]
        stub_rdb["StorageProcessed"].batch_stop_desktops_by_kind_ids(
            desktop_ids=ids,
            update_data={"status": "Stopping"},
            current_status="Started",
            batch_size=2,
        )
        get_all = stub_rdb["mock_table"].return_value.get_all
        assert get_all.call_count == 3

    def test_empty_id_list_no_dispatch(self, stub_rdb):
        stub_rdb["StorageProcessed"].batch_stop_desktops_by_kind_ids(
            desktop_ids=[],
            update_data={"status": "Stopping"},
            current_status="Started",
        )
        # No get_all calls; the for-range over an empty list is a no-op.
        get_all = stub_rdb["mock_table"].return_value.get_all
        assert get_all.call_count == 0

    def test_writes_to_domains_table(self, stub_rdb):
        stub_rdb["StorageProcessed"].batch_stop_desktops_by_kind_ids(
            desktop_ids=["d1"],
            update_data={"status": "Stopping"},
            current_status="Started",
        )
        # Confirm the table is "domains" (not "storage").
        # ``r.table("domains")`` is the call we care about.
        assert call("domains") in stub_rdb["mock_table"].call_args_list
