# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from handlers.resources import ResourcesHandler
from tests.conftest import FakeRow


class TestResourcesHandler:
    @pytest.fixture
    def handler(self):
        sio = AsyncMock()
        return ResourcesHandler(sio, "graphics")

    @pytest.mark.asyncio
    async def test_insert_emits_data_event(self, handler):
        row = FakeRow(id="g1", name="VGA")
        await handler.on_insert(row)
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "data"
        payload = json.loads(call_args[0][1])
        assert payload["table"] == "graphics"
        assert payload["data"]["id"] == "g1"

    @pytest.mark.asyncio
    async def test_update_emits_data_event(self, handler):
        old = FakeRow(id="g1")
        new = FakeRow(id="g1", name="QXL")
        await handler.on_update(old, new)
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "data"
        payload = json.loads(call_args[0][1])
        assert payload["data"]["name"] == "QXL"

    @pytest.mark.asyncio
    async def test_delete_emits_delete_event(self, handler):
        row = FakeRow(id="g1")
        await handler.on_delete(row)
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "delete"

    @pytest.mark.asyncio
    async def test_emits_to_admins_room(self, handler):
        row = FakeRow(id="g1")
        await handler.on_insert(row)
        call_kwargs = handler.socketio_server.emit.call_args[1]
        assert call_kwargs["namespace"] == "/administrators"
        assert call_kwargs["room"] == "admins"
