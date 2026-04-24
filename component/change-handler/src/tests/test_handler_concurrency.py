# SPDX-License-Identifier: AGPL-3.0-or-later

"""Concurrent-emit ordering for change-handler handlers.

The change-handler is a single-process asyncio service: every
`on_update` is a coroutine that hits an `AsyncMock` socket. With
asyncio's cooperative scheduling, multiple in-flight `on_update`
coroutines on the SAME id can interleave at every `await` inside
`BaseHandler.emit`.

What we want to pin:

1. **Per-call atomicity is NOT guaranteed.** Concurrent on_update
   calls may interleave their internal emits.
2. **No emits are dropped.** N concurrent calls produce N × emits-per-call
   total events on the socket.
3. **Per-room sequence equals per-call dispatch order.** When you
   filter the emit log by (event, room), the surviving payloads
   appear in the same relative order as the on_update calls that
   produced them — the frontend depends on this.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from tests.conftest import FakeRow


class TestSequentialUpdates:
    """`await` chain — strict total order."""

    @pytest.mark.asyncio
    async def test_categories_sequential_preserves_per_room_order(self):
        from handlers.categories import CategoriesHandler

        handler = CategoriesHandler(AsyncMock(), "categories")
        for i in range(5):
            await handler.on_update(
                FakeRow(id="cat1", name=f"v{i-1}"),
                FakeRow(id="cat1", name=f"v{i}"),
            )
        assert handler.socketio_server.emit.await_count == 15
        userspace_payloads = [
            json.loads(c[0][1])
            for c in handler.socketio_server.emit.call_args_list
            if c[1].get("namespace") == "/userspace" and c[1].get("room") == "cat1"
        ]
        assert [p["name"] for p in userspace_payloads] == [f"v{i}" for i in range(5)]

    @pytest.mark.asyncio
    async def test_targets_sequential_preserves_user_order(self):
        from handlers.targets import TargetsHandler

        handler = TargetsHandler(AsyncMock(), "targets")
        for i in range(4):
            await handler.on_update(
                FakeRow(id="t1", user_id="u1", name=f"old{i}"),
                FakeRow(id="t1", user_id="u1", name=f"new{i}"),
            )
        assert handler.socketio_server.emit.await_count == 8
        user_names = [
            json.loads(c[0][1])["name"]
            for c in handler.socketio_server.emit.call_args_list
            if c[0][0] == "targets_update" and c[1].get("room") == "u1"
        ]
        assert user_names == [f"new{i}" for i in range(4)]


class TestConcurrentUpdates:
    """`asyncio.gather` — interleaved but per-call sequence preserved."""

    @pytest.mark.asyncio
    async def test_no_emits_dropped_under_concurrent_load(self):
        from handlers.categories import CategoriesHandler

        handler = CategoriesHandler(AsyncMock(), "categories")
        n = 10
        coros = [
            handler.on_update(
                FakeRow(id="cat1", name=f"v{i-1}"),
                FakeRow(id="cat1", name=f"v{i}"),
            )
            for i in range(n)
        ]
        await asyncio.gather(*coros)
        assert handler.socketio_server.emit.await_count == 3 * n

    @pytest.mark.asyncio
    async def test_concurrent_user_updates_preserve_per_room_order(self):
        from handlers.users import UsersHandler

        handler = UsersHandler(AsyncMock(), "users")
        n = 8
        coros = [
            handler.on_update(
                FakeRow(id="u1", category="cat1", name="old"),
                FakeRow(
                    id="u1",
                    category="cat1",
                    additional_properties={"username": f"new{i}"},
                ),
            )
            for i in range(n)
        ]
        await asyncio.gather(*coros)

        user_room_names = [
            json.loads(c[0][1])["username"]
            for c in handler.socketio_server.emit.call_args_list
            if c[0][0] == "users_data" and c[1].get("room") == "u1"
        ]
        # FIFO order across the n coroutines is asyncio's documented
        # behaviour for awaits with no I/O between them.
        assert user_room_names == [f"new{i}" for i in range(n)]

    @pytest.mark.asyncio
    async def test_concurrent_bookings_preserve_user_room_order(self):
        from handlers.bookings import BookingsHandler

        handler = BookingsHandler(AsyncMock(), "bookings")
        n = 6

        def booking(i):
            return FakeRow(
                id=f"b{i}",
                user_id="u1",
                item_id="i1",
                item_type=None,
                start=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                end=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
                additional_properties={"title": f"t{i}"},
            )

        coros = [handler.on_update(booking(i - 1), booking(i)) for i in range(n)]
        await asyncio.gather(*coros)
        assert handler.socketio_server.emit.await_count == 2 * n
        booking_update_titles = [
            json.loads(c[0][1])["title"]
            for c in handler.socketio_server.emit.call_args_list
            if c[0][0] == "booking_update"
        ]
        assert booking_update_titles == [f"t{i}" for i in range(n)]
