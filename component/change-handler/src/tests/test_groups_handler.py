# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from tests.conftest import FakeRow


class TestGroupsHandler:
    @pytest.fixture
    def handler(self):
        from handlers.groups import GroupsHandler

        sio = AsyncMock()
        return GroupsHandler(sio, "groups")

    def _emit_calls(self, handler):
        calls = []
        for call in handler.socketio_server.emit.call_args_list:
            args, kwargs = call
            event = args[0]
            payload = json.loads(args[1])
            namespace = args[2] if len(args) > 2 else kwargs.get("namespace")
            room = args[3] if len(args) > 3 else kwargs.get("room")
            calls.append((event, payload, namespace, room))
        return calls

    @pytest.mark.asyncio
    async def test_insert_with_parent_category_emits_three_events(self, handler):
        await handler.on_insert(FakeRow(id="g1", name="Devs", parent_category="cat1"))
        calls = self._emit_calls(handler)
        assert len(calls) == 3
        rooms = [(ns, room) for _, _, ns, room in calls]
        assert ("/userspace", "g1") in rooms
        assert ("/administrators", "admins") in rooms
        assert ("/administrators", "cat1") in rooms

    @pytest.mark.asyncio
    async def test_insert_without_parent_category_skips_third_emit(self, handler):
        await handler.on_insert(FakeRow(id="g1", name="Devs"))
        calls = self._emit_calls(handler)
        assert len(calls) == 2
        rooms = [(ns, room) for _, _, ns, room in calls]
        assert ("/userspace", "g1") in rooms
        assert ("/administrators", "admins") in rooms

    @pytest.mark.asyncio
    async def test_update_emits_groups_data(self, handler):
        old = FakeRow(id="g1", name="Old")
        new = FakeRow(id="g1", name="New", parent_category="cat1")
        await handler.on_update(old, new)
        calls = self._emit_calls(handler)
        assert len(calls) == 3
        assert all(e == "groups_data" for e, _, _, _ in calls)
        assert all(p["name"] == "New" for _, p, _, _ in calls)

    @pytest.mark.asyncio
    async def test_delete_emits_groups_delete(self, handler):
        await handler.on_delete(FakeRow(id="g1", name="Devs", parent_category="cat1"))
        calls = self._emit_calls(handler)
        assert len(calls) == 3
        assert all(e == "groups_delete" for e, _, _, _ in calls)

    @pytest.mark.asyncio
    async def test_delete_without_parent_category_skips_third_emit(self, handler):
        await handler.on_delete(FakeRow(id="g1", name="Devs"))
        calls = self._emit_calls(handler)
        assert len(calls) == 2
