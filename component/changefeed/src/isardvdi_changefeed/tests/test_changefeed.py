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


class _AsyncCursorMock:
    """Stand-in for :class:`rethinkdb.asyncio_net.net_asyncio.AsyncioCursor`.

    Yields ``items`` one per ``__anext__`` await; if ``raise_after`` is
    set, raises that exception after the items are exhausted (instead
    of ``StopAsyncIteration``). ``close`` is an :class:`AsyncMock` so
    test-side assertions can pin "connection close happened on
    teardown" without coupling to driver internals.
    """

    def __init__(self, items, raise_after=None):
        self._items = list(items)
        self._raise_after = raise_after
        self.close = AsyncMock(name="cursor.close")

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            if self._raise_after is not None:
                raise self._raise_after
            raise StopAsyncIteration
        return self._items.pop(0)


def _patch_async_dedicated(conn):
    """Patch ``dedicated_async_connection`` to an :class:`AsyncMock`
    that returns ``conn``. The fork's helper is a coroutine; the mock
    must be awaitable too."""
    return patch(
        "isardvdi_changefeed.table_changefeed.dedicated_async_connection",
        new=AsyncMock(return_value=conn),
    )


def _make_async_query(cursor):
    """Build a Mock ``changes_query`` whose ``run`` is awaitable and
    resolves to ``cursor`` — mirrors the fork's
    ``await query.run(async_conn)`` shape."""
    q = MagicMock(name="changes-query")
    q.run = AsyncMock(return_value=cursor)
    return q


# Imported once so every test's AsyncMock helper is in scope.
from unittest.mock import AsyncMock  # noqa: E402


class TestConsumeCursor:
    """Pin the contract for the long-running cursor path (P2 #10,
    2026-05-02 — native asyncio):

    1. The cursor query runs against a connection from
       ``dedicated_async_connection()`` — NOT the shared pool. The
       pool is sized for short-query traffic; a process-lifetime
       cursor that held a pool slot would starve everything else.
    2. The connection is closed on every exit path (normal
       completion, publish raises, ``ReqlDriverError`` mid-stream,
       cancellation). A wedged socket must not outlive the cursor it
       fed.
    3. Iteration is native asyncio (``async for change in cursor:``)
       — exceptions raised by the cursor's ``__anext__`` propagate
       directly to the outer ``run`` loop's ``except ReqlDriverError``
       reconnect branch with no envelope / queue plumbing.
    """

    def test_cursor_runs_against_dedicated_async_connection(self):
        """The cursor's ``run`` must receive the dedicated async
        connection, and that socket must be closed when the cursor
        exits."""
        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()
        cursor = _AsyncCursorMock([{"new_val": {"table": "domains", "id": "d1"}}])
        changes_query = _make_async_query(cursor)

        with _patch_async_dedicated(dedicated_conn) as fake_dedicated:
            asyncio.run(cf._consume_cursor(changes_query))

        assert fake_dedicated.called, "cursor must use dedicated_async_connection"
        # The cursor's ``run`` is called with the async conn as the
        # only positional argument — never the shared-pool connection.
        changes_query.run.assert_awaited_once_with(dedicated_conn)
        # noreply_wait=False: the cursor stop already happened via
        # cursor.close(); we don't want to block process shutdown
        # waiting for any noreply replies to drain.
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)
        cursor.close.assert_awaited_once()
        cf._publish_change.assert_awaited_once()

    def test_cursor_close_runs_when_publish_raises(self):
        """If the publish path crashes mid-cursor, the ``finally``
        block must still close the dedicated socket and the cursor.
        Otherwise a wedged socket leaks per failure."""
        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock(side_effect=RuntimeError("publish boom"))

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()
        cursor = _AsyncCursorMock([{"new_val": {"table": "domains", "id": "d1"}}])
        changes_query = _make_async_query(cursor)

        with _patch_async_dedicated(dedicated_conn):
            with pytest.raises(RuntimeError, match="publish boom"):
                asyncio.run(cf._consume_cursor(changes_query))

        cursor.close.assert_awaited_once()
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)

    def test_cursor_close_runs_when_driver_errors_mid_iteration(self):
        """A driver-side error mid-iteration must let ``finally`` run
        — the connection should be closed before the exception
        propagates to the outer ``run`` loop's reconnect branch."""
        from rethinkdb.errors import ReqlDriverError

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()
        # First item delivers normally; second raises ReqlDriverError
        # — mimics the rdb driver dropping the cursor connection
        # during a stream.
        cursor = _AsyncCursorMock(
            [{"new_val": {"table": "domains", "id": "d1"}}],
            raise_after=ReqlDriverError("driver dropped"),
        )
        changes_query = _make_async_query(cursor)

        with _patch_async_dedicated(dedicated_conn):
            with pytest.raises(ReqlDriverError, match="driver dropped"):
                asyncio.run(cf._consume_cursor(changes_query))

        cursor.close.assert_awaited_once()
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)

    def test_cursor_close_failure_is_logged_and_swallowed(self):
        """If the cursor or connection ``close()`` raises (e.g. socket
        already torn down), the error must be logged but not
        propagated — the outer ``run`` loop's reconnect path is what
        handles recovery, and re-raising would obscure the original
        exception (or break the success path)."""
        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock(side_effect=OSError("socket already closed"))
        cursor = _AsyncCursorMock([])  # no changes; clean exit
        cursor.close = AsyncMock(side_effect=OSError("cursor torn down"))
        changes_query = _make_async_query(cursor)

        with _patch_async_dedicated(dedicated_conn):
            # No raise — both close failures must be swallowed.
            asyncio.run(cf._consume_cursor(changes_query))

        cursor.close.assert_awaited_once()
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)


class TestConsumeCursorAsyncResponsiveness:
    """Pin the P2 #10 contract: native ``async for change in cursor:``
    yields control back to the asyncio event loop on every
    ``__anext__`` await, so coroutines on the same loop keep getting
    scheduled. Replaces the worker-thread offload pattern that lived
    here between P2 #8 (2026-04) and P2 #10 (2026-05)."""

    def test_loop_stays_responsive_during_cursor_iteration(self):
        """A concurrent heartbeat coroutine must run while the cursor
        is mid-iteration. With native async iteration each
        ``__anext__`` await yields the loop; the heartbeat fires on
        every yield. The legacy on-loop sync iteration would freeze
        the loop until the entire cursor drained."""
        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()

        class _SlowAsyncCursor:
            """Each ``__anext__`` sleeps 50ms (async sleep yields the
            loop) before delivering the next item. After 3 deliveries,
            raises StopAsyncIteration."""

            def __init__(self, n=3):
                self._remaining = n
                self.close = AsyncMock()

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._remaining == 0:
                    raise StopAsyncIteration
                await asyncio.sleep(0.05)
                self._remaining -= 1
                return {"new_val": {"table": "domains", "id": "d"}}

        cursor = _SlowAsyncCursor(n=3)
        changes_query = _make_async_query(cursor)

        async def _runner():
            heartbeat_count = 0

            async def _heartbeat():
                nonlocal heartbeat_count
                while True:
                    await asyncio.sleep(0.02)
                    heartbeat_count += 1

            heartbeat_task = asyncio.create_task(_heartbeat())
            try:
                with _patch_async_dedicated(dedicated_conn):
                    await cf._consume_cursor(changes_query)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            return heartbeat_count

        beats = asyncio.run(_runner())

        # 3 cursor items × 50ms sleep ≈ 150ms total. Heartbeat at
        # 20ms cadence → ≥3 beats if the loop was actually running
        # concurrently with the cursor's per-anext awaits.
        assert beats >= 3, (
            f"loop appears starved during cursor iteration "
            f"(got {beats} heartbeat ticks, expected ≥3)"
        )
        assert cf._publish_change.await_count == 3

    def test_cursor_cancellation_closes_socket(self):
        """Cancelling the consumer task mid-publish must trigger a
        clean cursor + connection close. Otherwise long-lived
        cursors would leak their sockets on changefeed shutdown."""
        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()

        published = asyncio.Event()

        async def _publish_capture(change):
            published.set()
            await asyncio.sleep(60)  # block forever — cancel point

        cf._publish_change = _publish_capture

        # Cursor delivers one item then would block forever on
        # __anext__ — but we cancel before that happens.
        class _OneShotThenBlock:
            def __init__(self):
                self._delivered = False
                self.close = AsyncMock()

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._delivered:
                    await asyncio.sleep(60)  # block until cancelled
                    raise StopAsyncIteration  # unreachable
                self._delivered = True
                return {"new_val": {"table": "domains", "id": "d1"}}

        cursor = _OneShotThenBlock()
        changes_query = _make_async_query(cursor)

        async def _runner():
            with _patch_async_dedicated(dedicated_conn):
                task = asyncio.create_task(cf._consume_cursor(changes_query))
                # Wait until the consumer has pulled the first
                # change and is blocked in publish.
                await asyncio.wait_for(published.wait(), timeout=2.0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

        asyncio.run(_runner())

        # The dedicated socket must close even when cancellation
        # arrives mid-cursor — we don't want to leak it on shutdown.
        cursor.close.assert_awaited_once()
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)

    def test_cursor_run_failure_skips_close_path(self):
        """If ``await changes_query.run(conn)`` itself raises (e.g.
        the rdb server immediately rejects the changes query), the
        finally block must still close the connection — but cursor
        close is guarded since cursor was never assigned."""
        from rethinkdb.errors import ReqlDriverError

        cf = TableChangefeed([{"table": "domains"}], redis=MagicMock())
        cf._publish_change = AsyncMock()

        dedicated_conn = MagicMock(name="dedicated-cursor-conn")
        dedicated_conn.close = AsyncMock()

        changes_query = MagicMock(name="changes-query")
        changes_query.run = AsyncMock(side_effect=ReqlDriverError("connection lost"))

        with _patch_async_dedicated(dedicated_conn):
            with pytest.raises(ReqlDriverError, match="connection lost"):
                asyncio.run(cf._consume_cursor(changes_query))

        cf._publish_change.assert_not_called()
        # Connection still closes even though cursor was never built.
        dedicated_conn.close.assert_awaited_once_with(noreply_wait=False)
