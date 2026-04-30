#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``BackupsProcessed`` (tier 3.4 batch 2).

Migrated from inline rethink hits previously living in apiv4's
``services/admin/backups.py``. Validation, timestamp coercion, and
the notify-on-failure side-effect stay in apiv4 — these tests pin the
data-access contract.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.backups import backups as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.BackupsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.BackupsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "desc", lambda field: ("DESC", field))
    # Replace ReQL constructors so insert can call them under test.
    monkeypatch.setattr(mod.r, "now", lambda: "FAKE_NOW")
    monkeypatch.setattr(mod.r, "epoch_time", lambda s: ("EPOCH", s))
    monkeypatch.setattr(mod.r, "iso8601", lambda s: ("ISO", s))

    yield {"mock_table": mock_table, "Processed": mod.BackupsProcessed}


class TestListRecent:
    def test_returns_rows(self, stub_rdb):
        rows = [{"id": "b1"}, {"id": "b2"}]
        chain = stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.limit.return_value
        chain.run.return_value = rows
        result = stub_rdb["Processed"].list_recent(30)
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("backups")
        stub_rdb["mock_table"].return_value.order_by.assert_called_with(
            ("DESC", "timestamp")
        )
        stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.limit.assert_called_with(30)


class TestGet:
    def test_returns_full_row_when_no_pluck(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "b1"
        }
        assert stub_rdb["Processed"].get("b1") == {"id": "b1"}
        stub_rdb["mock_table"].return_value.get.assert_called_with("b1")

    def test_plucks_when_requested(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "id": "b1",
            "status": "ok",
        }
        result = stub_rdb["Processed"].get("b1", pluck=["id", "status"])
        assert result == {"id": "b1", "status": "ok"}
        stub_rdb["mock_table"].return_value.get.return_value.pluck.assert_called_with(
            "id", "status"
        )

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["Processed"].get("missing") is None


class TestInsert:
    def test_returns_rdb_result(self, stub_rdb):
        stub_rdb["mock_table"].return_value.insert.return_value.run.return_value = {
            "inserted": 1,
            "generated_keys": ["b-new"],
        }
        result = stub_rdb["Processed"].insert({"timestamp": 5, "status": "ok"})
        assert result == {"inserted": 1, "generated_keys": ["b-new"]}
        # ``timestamp`` is coerced via ``r.epoch_time``; ``received_at``
        # is stamped with ``r.now()`` and ``created_at`` defaults to it.
        inserted = stub_rdb["mock_table"].return_value.insert.call_args.args[0]
        assert inserted["timestamp"] == ("EPOCH", 5)
        assert inserted["received_at"] == "FAKE_NOW"
        assert inserted["created_at"] == "FAKE_NOW"
        assert inserted["status"] == "ok"

    def test_iso_timestamp_passes_through(self, stub_rdb):
        stub_rdb["mock_table"].return_value.insert.return_value.run.return_value = {
            "inserted": 1
        }
        stub_rdb["Processed"].insert(
            {"timestamp": "2026-04-30T12:00:00Z", "status": "ok"}
        )
        inserted = stub_rdb["mock_table"].return_value.insert.call_args.args[0]
        assert inserted["timestamp"] == ("ISO", "2026-04-30T12:00:00Z")

    def test_millisecond_timestamp_is_divided(self, stub_rdb):
        stub_rdb["mock_table"].return_value.insert.return_value.run.return_value = {
            "inserted": 1
        }
        stub_rdb["Processed"].insert({"timestamp": 1700000000000, "status": "ok"})
        inserted = stub_rdb["mock_table"].return_value.insert.call_args.args[0]
        # 1.7e12 > 1e10 so ms → seconds.
        assert inserted["timestamp"] == ("EPOCH", 1700000000.0)


class TestCount:
    def test_returns_count(self, stub_rdb):
        stub_rdb["mock_table"].return_value.count.return_value.run.return_value = 7
        assert stub_rdb["Processed"].count() == 7


class TestListOldIds:
    def test_returns_ids_after_keep(self, stub_rdb):
        chain = stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.skip.return_value.pluck.return_value
        chain.run.return_value = [{"id": "old-1"}, {"id": "old-2"}]
        assert stub_rdb["Processed"].list_old_ids(30) == ["old-1", "old-2"]
        stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.skip.assert_called_with(30)

    def test_empty_when_nothing_to_purge(self, stub_rdb):
        chain = stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.skip.return_value.pluck.return_value
        chain.run.return_value = []
        assert stub_rdb["Processed"].list_old_ids(30) == []


class TestDeleteMany:
    def test_returns_deleted_count(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.delete.return_value.run.return_value = {
            "deleted": 3
        }
        assert stub_rdb["Processed"].delete_many(["a", "b", "c"]) == 3
        stub_rdb["mock_table"].return_value.get_all.assert_called_with("a", "b", "c")

    def test_returns_zero_for_empty_input_without_query(self, stub_rdb):
        assert stub_rdb["Processed"].delete_many([]) == 0
        stub_rdb["mock_table"].return_value.get_all.assert_not_called()
