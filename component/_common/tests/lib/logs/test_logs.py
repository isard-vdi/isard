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


class _Chain:
    """Records the rdb chain so a test can assert on its shape.

    A MagicMock answers every attribute, so a dropped ``query = ...``
    reassignment still looks like a working chain. This records which
    node each call was made on, which is what pins it.
    """

    def __init__(self, recorder, op):
        self._recorder = recorder
        self.op = op

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self._recorder.calls.append((name, args, kwargs, self.op))
            return _Chain(self._recorder, name)

        return call

    def __getitem__(self, key):
        self._recorder.calls.append(("getitem", (key,), {}, self.op))
        return _Chain(self._recorder, "getitem")

    def run(self, conn, **kwargs):
        self._recorder.ran_on = self.op
        if self.op == "index_list":
            return self._recorder.indexes
        if self.op == "count":
            return self._recorder.groups
        return self._recorder.rows


class _Recorder:
    def __init__(self, rows, indexes=(), groups=0):
        self.calls = []
        self.rows = rows
        self.indexes = list(indexes)
        self.groups = groups
        self.ran_on = None
        self.tables = []

    def table(self, name):
        self.tables.append(name)
        return _Chain(self, "table")

    def op(self, name):
        return next(c for c in self.calls if c[0] == name)

    def ops(self, name):
        return [c for c in self.calls if c[0] == name]

    def filters(self):
        return [c[1][0] for c in self.calls if c[0] == "filter"]

    def sequence(self):
        """Call names in the order the chain applied them."""
        return [c[0] for c in self.calls if c[0] != "index_list"]


@pytest.fixture
def recorder(stub_rdb, monkeypatch):
    from isardvdi_common.lib.logs import logs as mod

    rec = _Recorder([{"id": "log-1"}])
    monkeypatch.setattr(mod.r, "table", rec.table)
    monkeypatch.setattr(mod.r, "minval", "MINVAL")
    monkeypatch.setattr(mod.r, "maxval", "MAXVAL")
    return rec


class TestListSimpleDesktop:
    def test_orders_through_the_index(self, recorder, stub_rdb):
        assert stub_rdb["Processed"].list_simple_desktop() == [{"id": "log-1"}]
        assert recorder.tables == ["logs_desktops"]
        # order_by without index= materialises the whole table and trips
        # rethink's 100k array limit on a table this size.
        assert recorder.op("order_by")[2] == {"index": ("DESC", "starting_time")}
        assert recorder.op("order_by")[3] == "table"

    def test_limit_is_the_query_that_runs(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_desktop(limit=25, offset=50)
        assert recorder.op("skip")[1] == (50,)
        assert recorder.op("limit")[1] == (25,)
        # Pins the dropped ``query = query.skip().limit()`` reassignment:
        # without it the unpaginated query is what runs.
        assert recorder.ran_on == "limit"

    def test_filters_use_the_writer_field_names(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_desktop(
            category_id="cat-1", desktop_id="desk-1", user_id="user-1"
        )
        assert recorder.filters() == [
            {"owner_category_id": "cat-1"},
            {"desktop_id": "desk-1"},
            {"owner_user_id": "user-1"},
        ]

    def test_date_range_narrows_the_index(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_desktop(
            start_date="2026-01-01", end_date="2026-01-31"
        )
        _, args, kwargs, on = recorder.op("between")
        assert on == "table"
        assert args == (
            ("ISO", "2026-01-01T00:00:00Z"),
            ("ISO", "2026-01-31T23:59:59Z"),
        )
        assert kwargs == {"index": "starting_time", "right_bound": "closed"}

    def test_no_dates_no_between(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_desktop()
        assert recorder.ops("between") == []


class TestListSimpleUser:
    def test_orders_through_the_index(self, recorder, stub_rdb):
        assert stub_rdb["Processed"].list_simple_user() == [{"id": "log-1"}]
        assert recorder.tables == ["logs_users"]
        assert recorder.op("order_by")[2] == {"index": ("DESC", "started_time")}
        assert recorder.op("order_by")[3] == "table"

    def test_limit_is_the_query_that_runs(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_user(limit=25, offset=50)
        assert recorder.op("skip")[1] == (50,)
        assert recorder.op("limit")[1] == (25,)
        assert recorder.ran_on == "limit"

    def test_filters_use_the_writer_field_names(self, recorder, stub_rdb):
        # api_logs_users.py writes owner_*; filtering on category_id /
        # user_id / group_id matches no row and silently returns [].
        stub_rdb["Processed"].list_simple_user(
            category_id="cat-1", user_id="user-1", group_id="group-1"
        )
        assert recorder.filters() == [
            {"owner_category_id": "cat-1"},
            {"owner_user_id": "user-1"},
            {"owner_group_id": "group-1"},
        ]

    def test_date_range_narrows_the_index(self, recorder, stub_rdb):
        # started_time, not starting_time: logs_users has no starting_time,
        # and rethink evaluates a missing field as null instead of erroring.
        stub_rdb["Processed"].list_simple_user(
            start_date="2026-01-01", end_date="2026-01-31"
        )
        _, args, kwargs, _ = recorder.op("between")
        assert args == (
            ("ISO", "2026-01-01T00:00:00Z"),
            ("ISO", "2026-01-31T23:59:59Z"),
        )
        assert kwargs == {"index": "started_time", "right_bound": "closed"}

    def test_open_ended_range(self, recorder, stub_rdb):
        stub_rdb["Processed"].list_simple_user(start_date="2026-01-01")
        assert recorder.op("between")[1] == (("ISO", "2026-01-01T00:00:00Z"), "MAXVAL")

    def test_empty_strings_are_not_filters(self, recorder, stub_rdb):
        # The route declares these as ``str = None``, so ``?user_id=&start_date=``
        # arrives as "" — an empty start_date would build the invalid
        # timestamp "T00:00:00Z" and 500.
        stub_rdb["Processed"].list_simple_user(
            category_id="", user_id="", group_id="", start_date="", end_date=""
        )
        assert recorder.filters() == []
        assert recorder.ops("between") == []


class TestBuildQueryOrdering:
    """``_build_query`` ordering, which decides whether the query streams."""

    @pytest.fixture
    def build(self, stub_rdb, monkeypatch):
        from isardvdi_common.lib.logs import logs as mod

        def _build(indexes, parsed, **kwargs):
            rec = _Recorder([], indexes=indexes)
            monkeypatch.setattr(mod.r, "table", rec.table)
            stub_rdb["Processed"]._build_query("logs_users", parsed, **kwargs)
            return rec

        return _build

    def _parsed(self, column, direction="desc", **extra):
        return {
            "order": [{"column": 0, "dir": direction}],
            "columns": [{"data": column}],
            **extra,
        }

    def test_indexed_column_orders_through_the_index(self, build):
        rec = build(["started_time"], self._parsed("started_time"))
        assert rec.op("order_by")[2] == {"index": ("DESC", "started_time")}
        assert rec.op("order_by")[3] == "table"

    def test_non_indexed_column_sorts_after_the_filters(self, build):
        # Sorting first materialises the whole table and trips rethink's
        # 100k array limit; sorting last only sees what the filters left.
        rec = build(
            ["started_time"],
            self._parsed("owner_user_name"),
            scope_category_id="cat-1",
        )
        assert rec.op("order_by")[1] == (("DESC", "owner_user_name"),)
        assert rec.op("order_by")[2] == {}
        assert rec.sequence() == ["filter", "order_by"]

    def test_range_rides_the_index_when_the_order_does_not(self, build):
        rec = build(
            ["started_time"],
            self._parsed(
                "owner_user_name",
                range={
                    "field": "started_time",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                },
            ),
        )
        assert rec.op("between")[2] == {"index": "started_time"}
        assert rec.op("between")[3] == "table"
        assert rec.sequence() == ["between", "order_by"]

    def test_range_falls_back_to_filter_when_the_order_claims_the_index(self, build):
        # A table is walked through one index only, so an indexed order on
        # another field leaves the range no index to ride.
        rec = build(
            ["started_time", "owner_user_id"],
            self._parsed(
                "owner_user_id",
                range={
                    "field": "started_time",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                },
            ),
        )
        assert rec.ops("between") == []
        assert rec.op("order_by")[2] == {"index": ("DESC", "owner_user_id")}
        assert rec.sequence() == ["order_by", "filter"]

    def test_incomplete_range_is_ignored(self, build):
        rec = build(
            ["started_time"],
            self._parsed("started_time", range={"field": "started_time"}),
        )
        assert rec.ops("between") == []
        assert rec.filters() == []


class TestGroupingViews:
    """The desktop/user grouping views of ``query_paginated``."""

    @pytest.fixture
    def grouped(self, stub_rdb, monkeypatch):
        from isardvdi_common.lib.logs import logs as mod

        def _run(table, view, parsed, indexes=("starting_time", "started_time")):
            rec = _Recorder([{"count": 3}], indexes=indexes, groups=7)
            monkeypatch.setattr(mod.r, "table", rec.table)
            monkeypatch.setattr(mod.r, "minval", "MINVAL")
            monkeypatch.setattr(mod.r, "maxval", "MAXVAL")
            return rec, stub_rdb["Processed"].query_paginated(table, parsed, view=view)

        return _run

    def _parsed(self, field, direction="desc", **extra):
        return {
            "start": 0,
            "length": 25,
            "order": [{"column": 0, "dir": direction}],
            "columns": [{"data": field}],
            **extra,
        }

    def test_desktop_grouping_groups_the_filtered_query(self, grouped):
        # Grouping the bare table both blows the 100k array limit and drops
        # the date range: the group has to sit on the narrowed query.
        rec, _ = grouped(
            "logs_desktops",
            "desktop_grouping",
            self._parsed(
                "count",
                range={
                    "field": "starting_time",
                    "start": "2026-01-01",
                    "end": "2026-01-31",
                },
            ),
        )
        assert rec.op("between")[2] == {"index": "starting_time"}
        sequence = rec.sequence()
        assert sequence.index("between") < sequence.index("group")
        # group by field, not index: the narrowed query is no longer a table.
        assert rec.op("group")[1] == ("desktop_id",)
        assert rec.op("group")[2] == {}

    def test_grouping_does_not_order_the_rows(self, grouped):
        # The order names a column of the grouped result, so ordering the
        # rows would be both meaningless and a full sort of the table.
        rec, _ = grouped("logs_users", "user_grouping", self._parsed("count"))
        order_ops = rec.ops("order_by")
        assert len(order_ops) == 1
        assert order_ops[0][3] == "getitem"

    def test_grouping_orders_the_groups(self, grouped):
        rec, _ = grouped("logs_users", "user_grouping", self._parsed("count"))
        assert rec.op("order_by")[1] == (("DESC", "count"),)

    def test_grouping_ignores_an_order_the_groups_do_not_carry(self, grouped):
        rec, _ = grouped("logs_users", "user_grouping", self._parsed("request_ip"))
        assert rec.ops("order_by") == []

    def test_grouping_counts_groups_not_rows(self, grouped):
        # Both counts describe what the view paginates, which is groups.
        _, result = grouped("logs_users", "user_grouping", self._parsed("count"))
        assert result["recordsTotal"] == 7
        assert result["recordsFiltered"] == 7

    def test_grouping_pages_the_groups(self, grouped):
        rec, _ = grouped(
            "logs_users",
            "user_grouping",
            self._parsed("count", start=50, length=10),
        )
        assert rec.op("skip")[1] == (50,)
        assert rec.op("limit")[1] == (10,)
        assert rec.ran_on == "limit"


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
