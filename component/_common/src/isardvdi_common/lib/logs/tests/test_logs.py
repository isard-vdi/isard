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

    def test_manager_filters_by_category(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.order_by.return_value.skip.return_value.limit.return_value.run.return_value = (
            []
        )
        stub_rdb["Processed"].list_simple_user(category_id="cat-1")
        assert stub_rdb["mock_table"].return_value.filter.call_args_list[0].args[0] == {
            "category_id": "cat-1"
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
