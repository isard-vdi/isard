# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestCategoriesHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.categories import CategoriesHandler

        sio = AsyncMock()
        return CategoriesHandler(sio, "categories")

    @pytest.mark.asyncio
    async def test_on_insert_emits_to_three_rooms(self, handler):
        row = FakeRow(id="cat1", name="Default")
        await handler.on_insert(row)
        assert handler.socketio_server.emit.await_count == 3

    @pytest.mark.asyncio
    async def test_on_insert_uses_id_as_room(self, handler):
        row = FakeRow(id="cat1", name="Default")
        await handler.on_insert(row)

        rooms = [
            call[1]["room"] for call in handler.socketio_server.emit.call_args_list
        ]
        assert rooms.count("cat1") == 2  # userspace + administrators
        assert "admins" in rooms

    @pytest.mark.asyncio
    async def test_on_insert_emits_exact_namespace_room_triples(self, handler):
        """Pin full (event, namespace, room) contract for all 3 insert emits."""
        row = FakeRow(id="cat1", name="Default")
        await handler.on_insert(row)

        triples = set()
        for call in handler.socketio_server.emit.call_args_list:
            args, kwargs = call
            event = args[0]
            namespace = args[2] if len(args) > 2 else kwargs.get("namespace")
            room = args[3] if len(args) > 3 else kwargs.get("room")
            triples.add((event, namespace, room))

        assert ("categories_data", "/userspace", "cat1") in triples
        assert ("categories_data", "/administrators", "admins") in triples
        assert ("categories_data", "/administrators", "cat1") in triples

    @pytest.mark.asyncio
    async def test_on_update_serializes_model(self, handler):
        old = FakeRow(id="cat1", name="Old")
        new = FakeRow(id="cat1", name="New")
        await handler.on_update(old, new)

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["name"] == "New"

    @pytest.mark.asyncio
    async def test_on_update_all_three_payloads_carry_new_value(self, handler):
        """All 3 emits must carry the NEW name, not the old one."""
        old = FakeRow(id="cat1", name="Old")
        new = FakeRow(id="cat1", name="New")
        await handler.on_update(old, new)

        events = []
        payloads = []
        for call in handler.socketio_server.emit.call_args_list:
            events.append(call[0][0])
            payloads.append(json.loads(call[0][1]))
        assert events == ["categories_data"] * 3
        assert all(p["name"] == "New" for p in payloads)

    @pytest.mark.asyncio
    async def test_on_delete_emits_delete_event(self, handler):
        row = FakeRow(id="cat1")
        await handler.on_delete(row)

        events = [call[0][0] for call in handler.socketio_server.emit.call_args_list]
        assert all(e == "categories_delete" for e in events)

    @pytest.mark.asyncio
    async def test_on_delete_emits_to_same_three_rooms(self, handler):
        row = FakeRow(id="cat1", name="Default")
        await handler.on_delete(row)

        rooms = set()
        for call in handler.socketio_server.emit.call_args_list:
            args, kwargs = call
            rooms.add(args[3] if len(args) > 3 else kwargs.get("room"))
        assert rooms == {"cat1", "admins"}
