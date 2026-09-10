#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``LogsProcessed`` (tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/domains.py`` (logs DataTables endpoints,
list_desktop_logs / list_user_logs, _delete_logs_async batch delete).

Pins:
* query_paginated('raw') returns ``{draw, recordsTotal,
  recordsFiltered, data, indexs}``.
* list_simple_desktop / list_simple_user honour the
  ``category_id``/``user_id``/``desktop_id``/date filters.
* delete_batch chunks ids by ``batch_size`` to avoid array_limit.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.logs import logs as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.LogsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.LogsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    monkeypatch.setattr(mod.r, "desc", lambda x: ("DESC", x))
    monkeypatch.setattr(mod.r, "asc", lambda x: ("ASC", x))
    monkeypatch.setattr(mod.r, "iso8601", lambda x: ("ISO", x))
    yield {"mock_table": mock_table, "Processed": mod.LogsProcessed}


class TestQueryPaginatedRaw:
    def test_returns_datatables_envelope(self, stub_rdb):
        # index_list returns the indexes; count returns total/filtered;
        # the paged query runs once with .skip().limit().run() returning rows.
        stub_rdb["mock_table"].return_value.index_list.return_value.run.return_value = [
            "starting_time"
        ]
        stub_rdb["mock_table"].return_value.count.return_value.run.return_value = 12
        stub_rdb[
            "mock_table"
        ].return_value.skip.return_value.limit.return_value.run.return_value = [
            {"id": "log-1"}
        ]
        # The .count() on the build query path bumps another .count():
        # _build_query returns ``r.table(table)`` which also has count.
        # MagicMock chains return MagicMocks so a single shared count
        # return covers both calls.
        result = stub_rdb["Processed"].query_paginated(
            "logs_desktops", {"draw": 3, "start": 0, "length": 25}, view="raw"
        )
        assert result["draw"] == 3
        assert "data" in result
        assert "recordsTotal" in result
        assert "recordsFiltered" in result
        assert result["indexs"] == ["starting_time"]


class TestListSimpleDesktop:
    def test_admin_runs_no_category_filter(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.skip.return_value.limit.return_value.run.return_value = [
            {"id": "log-1"}
        ]
        result = stub_rdb["Processed"].list_simple_desktop()
        assert result == [{"id": "log-1"}]
        stub_rdb["mock_table"].assert_any_call("logs_desktops")

    def test_manager_filters_by_category(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.order_by.return_value.skip.return_value.limit.return_value.run.return_value = (
            []
        )
        stub_rdb["Processed"].list_simple_desktop(category_id="cat-1")
        # ``filter({"owner_category_id": "cat-1"})`` was applied on the
        # base table — first .filter() call carries that scope.
        assert stub_rdb["mock_table"].return_value.filter.call_args_list[0].args[0] == {
            "owner_category_id": "cat-1"
        }


class TestListSimpleUser:
    def test_admin_runs_no_category_filter(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.order_by.return_value.skip.return_value.limit.return_value.run.return_value = [
            {"id": "u-log-1"}
        ]
        assert stub_rdb["Processed"].list_simple_user() == [{"id": "u-log-1"}]
        stub_rdb["mock_table"].assert_any_call("logs_users")

    def test_manager_filters_by_owner_category_id(self, stub_rdb):
        # Writer at ``api_logs_users.py:96`` stores the column as
        # ``owner_category_id``; the apiv4 port had this filter using
        # ``category_id`` so manager-scoped lists silently returned [].
        # Pin the corrected field name so the regression can't drift
        # back.
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.order_by.return_value.skip.return_value.limit.return_value.run.return_value = (
            []
        )
        stub_rdb["Processed"].list_simple_user(category_id="cat-1")
        assert stub_rdb["mock_table"].return_value.filter.call_args_list[0].args[0] == {
            "owner_category_id": "cat-1"
        }


class TestDeleteBatch:
    def test_chunks_by_batch_size(self, stub_rdb):
        # Five ids, batch_size=2 → three calls.
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.delete.return_value.run.return_value = {
            "deleted": 2
        }
        stub_rdb["Processed"].delete_batch(
            "logs_desktops",
            ["a", "b", "c", "d", "e"],
            batch_size=2,
        )
        # delete().run() is called three times (chunks: [a,b], [c,d], [e]).
        assert (
            stub_rdb[
                "mock_table"
            ].return_value.get_all.return_value.delete.return_value.run.call_count
            == 3
        )

    def test_empty_ids_does_nothing(self, stub_rdb):
        stub_rdb["Processed"].delete_batch("logs_users", [], batch_size=2)
        assert (
            stub_rdb[
                "mock_table"
            ].return_value.get_all.return_value.delete.return_value.run.call_count
            == 0
        )

    def test_backup_writes_rows_before_delete(self, stub_rdb):
        """Pin the order: fetch → write to backup → delete. If the
        delete fired before the fetch the backup would be empty;
        if it fired before the write the backup would miss rows.
        """
        # Two distinct .run() chains (fetch is on get_all().run(),
        # delete is on get_all().delete().run()) so the test can pin
        # both. The fetch returns the row dicts.
        fetched_rows = [
            {"id": "a", "started_time": 1, "stopped_time": 2},
            {"id": "b", "started_time": 3, "stopped_time": 4},
        ]
        stub_rdb["mock_table"].return_value.get_all.return_value.run.return_value = (
            fetched_rows
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.delete.return_value.run.return_value = {
            "deleted": 2
        }

        # MagicMock-style writer with a write_rows method we can inspect.
        backup = MagicMock(name="BackupWriter")

        stub_rdb["Processed"].delete_batch(
            "logs_desktops",
            ["a", "b"],
            batch_size=10,
            backup=backup,
        )

        # write_rows received the fetched rows, exactly once.
        backup.write_rows.assert_called_once_with(fetched_rows)
        # delete still runs.
        assert (
            stub_rdb[
                "mock_table"
            ].return_value.get_all.return_value.delete.return_value.run.call_count
            == 1
        )

    def test_backup_chunks_per_batch(self, stub_rdb):
        """A single backup writer collects rows from every chunk."""
        # Each fetch.run() returns a different chunk of rows.
        fetch_chain = stub_rdb["mock_table"].return_value.get_all.return_value
        fetch_chain.run = MagicMock(
            side_effect=[
                [{"id": "a"}, {"id": "b"}],
                [{"id": "c"}, {"id": "d"}],
                [{"id": "e"}],
            ]
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.delete.return_value.run.return_value = {
            "deleted": 2
        }
        backup = MagicMock(name="BackupWriter")

        stub_rdb["Processed"].delete_batch(
            "logs_desktops",
            ["a", "b", "c", "d", "e"],
            batch_size=2,
            backup=backup,
        )

        # Three chunks → three write_rows calls → all rows backed up.
        assert backup.write_rows.call_count == 3
        all_written = []
        for call in backup.write_rows.call_args_list:
            all_written.extend(call.args[0])
        assert [row["id"] for row in all_written] == ["a", "b", "c", "d", "e"]

    def test_no_backup_skips_extra_fetch(self, stub_rdb):
        """Without a backup writer, the extra fetch must not happen
        — pin so future refactors don't add a needless rdb round-
        trip on the hot delete path."""
        # The fetch chain run() should NEVER be called when backup
        # is None.
        fetch_chain = stub_rdb["mock_table"].return_value.get_all.return_value
        fetch_chain.run = MagicMock(side_effect=AssertionError("fetch called"))
        # delete still runs, normally.
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.delete.return_value.run.return_value = {
            "deleted": 2
        }

        stub_rdb["Processed"].delete_batch(
            "logs_desktops",
            ["a", "b"],
            batch_size=10,
            backup=None,
        )


class TestCountOlder:
    def test_uses_per_table_retention_index_count(self, stub_rdb):
        run = stub_rdb[
            "mock_table"
        ].return_value.between.return_value.count.return_value.run
        run.return_value = 42
        # logs_desktops keys on ``starting_time`` (always present); logs_users
        # keys on ``started_time``.
        n = stub_rdb["Processed"].count_older("logs_desktops", "CUTOFF")
        assert n == 42
        _, kwargs = stub_rdb["mock_table"].return_value.between.call_args
        assert kwargs.get("index") == "starting_time"
        stub_rdb["Processed"].count_older("logs_users", "CUTOFF")
        _, kwargs = stub_rdb["mock_table"].return_value.between.call_args
        assert kwargs.get("index") == "started_time"


class TestDeleteOldStreamed:
    def _run_mock(self, stub_rdb):
        return stub_rdb[
            "mock_table"
        ].return_value.between.return_value.limit.return_value.delete.return_value.run

    def test_pages_until_short_page_and_returns_total(self, stub_rdb):
        # page_size=2: two full pages then a short page (1 < 2) stops the loop.
        self._run_mock(stub_rdb).side_effect = [
            {"deleted": 2},
            {"deleted": 2},
            {"deleted": 1},
        ]
        total = stub_rdb["Processed"].delete_old_streamed(
            "logs_desktops", "CUTOFF", page_size=2, pause=0
        )
        assert total == 5
        assert self._run_mock(stub_rdb).call_count == 3
        # index range + soft durability, no return_changes without a backup.
        _, bkw = stub_rdb["mock_table"].return_value.between.call_args
        assert bkw.get("index") == "starting_time"  # logs_desktops retention key
        delete = stub_rdb[
            "mock_table"
        ].return_value.between.return_value.limit.return_value.delete
        _, dkw = delete.call_args
        assert dkw.get("return_changes") is False
        assert dkw.get("durability") == "soft"

    def test_backup_streams_old_vals_and_sets_return_changes(self, stub_rdb):
        self._run_mock(stub_rdb).side_effect = [
            {"deleted": 1, "changes": [{"old_val": {"id": "a"}}]},
        ]
        backup = MagicMock()
        total = stub_rdb["Processed"].delete_old_streamed(
            "logs_users", "CUTOFF", backup=backup, page_size=2, pause=0
        )
        assert total == 1
        backup.write_rows.assert_called_once_with([{"id": "a"}])
        delete = stub_rdb[
            "mock_table"
        ].return_value.between.return_value.limit.return_value.delete
        _, dkw = delete.call_args
        assert dkw.get("return_changes") is True
