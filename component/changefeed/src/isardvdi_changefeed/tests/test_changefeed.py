# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the changefeed service — the RethinkDB → Redis bridge.

Focus areas:
- `sanitize()` — converts datetimes to ISO strings, recurses into
  dicts/lists, leaves primitives alone.
- `TableChangefeed.__init__` — derives the stream-table set from
  the config.
- `TableChangefeed._wait_for_tables` — startup gate. The
  `isardvdi-apiv4-migration` skill pins this as a readiness check
  that crashes with 'Table does not exist' if skipped; assert it
  returns once all required tables exist and keeps polling while
  some are missing.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_changefeed.table_changefeed import TableChangefeed, sanitize


class TestSanitize:
    def test_primitive_passthrough(self):
        assert sanitize(42) == 42
        assert sanitize("hello") == "hello"
        assert sanitize(None) is None
        assert sanitize(True) is True

    def test_datetime_becomes_isoformat(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert sanitize(dt) == "2026-01-15T10:30:00+00:00"

    def test_dict_is_recursed(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert sanitize({"ts": dt, "name": "x"}) == {
            "ts": "2026-01-15T10:30:00+00:00",
            "name": "x",
        }

    def test_list_is_recursed(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert sanitize([dt, "plain", 7]) == [
            "2026-01-15T10:30:00+00:00",
            "plain",
            7,
        ]

    def test_nested_structure(self):
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        payload = {
            "items": [{"created": dt, "tags": ["a", "b"]}],
            "count": 1,
        }
        result = sanitize(payload)
        assert result["items"][0]["created"] == "2026-01-15T10:30:00+00:00"
        assert result["items"][0]["tags"] == ["a", "b"]
        assert result["count"] == 1


class TestTableChangefeedInit:
    def test_stream_tables_derived_from_config(self):
        tables = [
            {"table": "domains", "stream": True},
            {"table": "users", "stream": True},
            {"table": "categories"},  # no stream
        ]
        cf = TableChangefeed(tables, redis=MagicMock())
        assert cf.stream_tables == {"domains", "users"}

    def test_no_stream_tables_when_flag_absent(self):
        tables = [{"table": "a"}, {"table": "b"}]
        cf = TableChangefeed(tables, redis=MagicMock())
        assert cf.stream_tables == set()

    def test_stream_false_excluded(self):
        tables = [
            {"table": "a", "stream": True},
            {"table": "b", "stream": False},
        ]
        cf = TableChangefeed(tables, redis=MagicMock())
        assert cf.stream_tables == {"a"}


class TestWaitForTables:
    """The readiness gate — runs until `r.table_list()` returns every
    required table. Use tiny delays and mock the connection so the
    test completes instantly.
    """

    def _make_cf(self, tables):
        cf = TableChangefeed(tables, redis=MagicMock())
        # Replace the rethink connection context + the connection so
        # `r.table_list().run(self._rdb_connection)` hits our mock.
        cf._rdb_context = MagicMock()
        cf._rdb_context.return_value.__enter__ = MagicMock(return_value=None)
        cf._rdb_context.return_value.__exit__ = MagicMock(return_value=False)
        cf._rdb_connection = MagicMock()
        return cf

    def test_returns_immediately_when_all_tables_present(self):
        tables = [{"table": "domains"}, {"table": "users"}]
        cf = self._make_cf(tables)

        with patch("isardvdi_changefeed.table_changefeed.r") as mock_r:
            table_list = MagicMock()
            table_list.run.return_value = ["domains", "users", "other"]
            mock_r.table_list.return_value = table_list

            # If the loop runs more than once without exiting, asyncio.wait_for
            # would time out.
            asyncio.run(asyncio.wait_for(cf._wait_for_tables(), timeout=1.0))

    def test_polls_until_all_tables_exist(self):
        tables = [{"table": "domains"}, {"table": "users"}]
        cf = self._make_cf(tables)

        # AsyncMock returns a no-op coroutine; avoids patching
        # asyncio.sleep directly (which would recurse into itself).
        from unittest.mock import AsyncMock

        with patch("isardvdi_changefeed.table_changefeed.r") as mock_r, patch(
            "isardvdi_changefeed.table_changefeed.asyncio.sleep", new=AsyncMock()
        ):
            table_list = MagicMock()
            # First poll: missing users. Second poll: all there.
            table_list.run.side_effect = [["domains"], ["domains", "users"]]
            mock_r.table_list.return_value = table_list

            asyncio.run(asyncio.wait_for(cf._wait_for_tables(), timeout=1.0))
            assert table_list.run.call_count == 2

    def test_tolerates_exception_during_readiness_check(self):
        """DB connect might fail transiently — the loop must catch and
        keep polling, not crash the changefeed."""
        tables = [{"table": "x"}]
        cf = self._make_cf(tables)

        # AsyncMock returns a no-op coroutine; avoids patching
        # asyncio.sleep directly (which would recurse into itself).
        from unittest.mock import AsyncMock

        with patch("isardvdi_changefeed.table_changefeed.r") as mock_r, patch(
            "isardvdi_changefeed.table_changefeed.asyncio.sleep", new=AsyncMock()
        ):
            table_list = MagicMock()
            table_list.run.side_effect = [RuntimeError("db not ready"), ["x"]]
            mock_r.table_list.return_value = table_list

            asyncio.run(asyncio.wait_for(cf._wait_for_tables(), timeout=1.0))
            assert table_list.run.call_count == 2


class TestConsumeCursor:
    """Pin the contract for the long-running cursor path:

    1. The cursor query runs against a connection from
       ``dedicated_connection()`` — NOT the shared pool. The pool is
       sized for short-query traffic; a process-lifetime cursor that
       held a pool slot would starve everything else.
    2. The cursor connection's ``close()`` is invoked on every exit
       path (normal completion, publish raises, exception in driver),
       so a wedged socket can't outlive the cursor it fed.

    These tests drive ``_consume_cursor`` directly rather than the
    full ``run()`` while-loop. The while-loop is already pinned via
    the ``_wait_for_tables`` tests above; isolating the cursor
    method avoids fighting the patched ``asyncio.sleep`` and yields
    a deterministic single trip through the cursor.
    """

    def test_cursor_runs_against_dedicated_connection(self):
        """The cursor's ``run`` must receive the dedicated connection,
        and that socket must be closed when the cursor exits."""
        from unittest.mock import AsyncMock

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        changes_query = MagicMock(name="changes-query")
        changes_query.run.return_value = iter(
            [{"new_val": {"table": "domains", "id": "d1"}}]
        )

        with patch(
            "isardvdi_changefeed.table_changefeed.dedicated_connection",
            return_value=dedicated_conn,
        ) as fake_dedicated:
            asyncio.run(cf._consume_cursor(changes_query))

        assert fake_dedicated.called, "cursor must use dedicated_connection"
        # The cursor's ``run`` is called with the dedicated socket
        # as the only positional argument — never the shared-pool
        # connection.
        changes_query.run.assert_called_once_with(dedicated_conn)
        assert (
            dedicated_conn.close.called
        ), "dedicated cursor connection must be closed on cursor teardown"
        cf._publish_change.assert_awaited_once()

    def test_cursor_close_runs_when_publish_raises(self):
        """If the publish path crashes mid-cursor, the ``finally``
        block must still close the dedicated socket. Otherwise a
        wedged socket leaks per failure."""
        from unittest.mock import AsyncMock

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock(side_effect=RuntimeError("publish boom"))

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        changes_query = MagicMock(name="changes-query")
        changes_query.run.return_value = iter(
            [{"new_val": {"table": "domains", "id": "d1"}}]
        )

        with patch(
            "isardvdi_changefeed.table_changefeed.dedicated_connection",
            return_value=dedicated_conn,
        ):
            with pytest.raises(RuntimeError, match="publish boom"):
                asyncio.run(cf._consume_cursor(changes_query))

        assert (
            dedicated_conn.close.called
        ), "cursor connection must close even when publish raises"

    def test_cursor_close_runs_when_driver_errors_mid_iteration(self):
        """A driver-side error mid-iteration must still let
        ``finally`` run — the connection should be closed before
        the exception propagates."""
        from unittest.mock import AsyncMock

        from rethinkdb.errors import ReqlDriverError

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")

        # An iterator that raises mid-iteration — mimics the rdb
        # driver dropping the cursor connection during a stream.
        def _broken_cursor():
            yield {"new_val": {"table": "domains", "id": "d1"}}
            raise ReqlDriverError("driver dropped")

        changes_query = MagicMock(name="changes-query")
        changes_query.run.return_value = _broken_cursor()

        with patch(
            "isardvdi_changefeed.table_changefeed.dedicated_connection",
            return_value=dedicated_conn,
        ):
            with pytest.raises(ReqlDriverError):
                asyncio.run(cf._consume_cursor(changes_query))

        assert (
            dedicated_conn.close.called
        ), "cursor connection must close even on driver error"

    def test_cursor_close_failure_is_logged_and_swallowed(self):
        """If ``close()`` itself raises (e.g. socket already torn
        down), the error must be logged but not propagated — the
        outer ``run`` loop's reconnect path is what handles
        recovery, and re-raising would obscure the original
        exception (or break the success path)."""
        from unittest.mock import AsyncMock

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close.side_effect = OSError("socket already closed")
        changes_query = MagicMock(name="changes-query")
        changes_query.run.return_value = iter([])  # no changes; clean exit

        with patch(
            "isardvdi_changefeed.table_changefeed.dedicated_connection",
            return_value=dedicated_conn,
        ):
            # No raise — the close failure must not surface here.
            asyncio.run(cf._consume_cursor(changes_query))

        assert dedicated_conn.close.called
