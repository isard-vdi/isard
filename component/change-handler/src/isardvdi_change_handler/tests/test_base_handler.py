# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.handlers.base import BaseHandler, json_dumps
from isardvdi_change_handler.tests.conftest import FakeChange, FakeRow


class TestJsonDumps:
    def test_serializes_dict(self):
        assert json_dumps({"key": "val"}) == '{"key": "val"}'

    def test_serializes_datetime(self):
        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = json.loads(json_dumps({"ts": dt}))
        assert result["ts"] == "2025-01-15T10:30:00"

    def test_serializes_pydantic_model(self):
        row = FakeRow(id="r1", name="test")
        result = json.loads(json_dumps(row))
        assert result["id"] == "r1"
        assert result["name"] == "test"

    def test_serializes_pydantic_model_excludes_none(self):
        row = FakeRow(id="r1")
        result = json.loads(json_dumps(row))
        assert "name" not in result

    def test_serializes_pydantic_model_nested_in_dict(self):
        row = FakeRow(id="r1", name="test")
        result = json.loads(json_dumps({"table": "foo", "data": row}))
        assert result["table"] == "foo"
        assert result["data"]["id"] == "r1"

    def test_serializes_additional_properties(self):
        row = FakeRow(id="r1", additional_properties={"extra": "value"})
        result = json.loads(json_dumps(row))
        assert result["extra"] == "value"

    def test_raises_for_unknown_types(self):
        with pytest.raises(TypeError):
            json_dumps({"obj": object()})


class TestBaseHandler:
    @pytest.fixture
    def handler(self):
        sio = AsyncMock()
        return BaseHandler(sio, "test_table")

    @pytest.mark.asyncio
    async def test_handle_insert(self, handler):
        handler.on_insert = AsyncMock()
        row = FakeRow(id="1", name="test")
        change = FakeChange(new_val=row, old_val=None)
        await handler.handle(change)
        handler.on_insert.assert_awaited_once_with(row)

    @pytest.mark.asyncio
    async def test_handle_update(self, handler):
        handler.on_update = AsyncMock()
        old = FakeRow(id="1", name="original")
        new = FakeRow(id="1", name="updated")
        change = FakeChange(new_val=new, old_val=old)
        await handler.handle(change)
        handler.on_update.assert_awaited_once_with(old, new)

    @pytest.mark.asyncio
    async def test_handle_delete(self, handler):
        handler.on_delete = AsyncMock()
        row = FakeRow(id="1", name="deleted")
        change = FakeChange(new_val=None, old_val=row)
        await handler.handle(change)
        handler.on_delete.assert_awaited_once_with(row)

    @pytest.mark.asyncio
    async def test_handle_ignores_empty_change(self, handler):
        handler.on_insert = AsyncMock()
        handler.on_update = AsyncMock()
        handler.on_delete = AsyncMock()
        change = FakeChange(new_val=None, old_val=None)
        await handler.handle(change)
        handler.on_insert.assert_not_awaited()
        handler.on_update.assert_not_awaited()
        handler.on_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_on_insert_emits(self, handler):
        row = FakeRow(id="1")
        await handler.on_insert(row)
        handler.socketio_server.emit.assert_awaited_once()
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "test_table_add"

    @pytest.mark.asyncio
    async def test_default_on_update_emits(self, handler):
        old = FakeRow(id="1")
        new = FakeRow(id="1", name="new")
        await handler.on_update(old, new)
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "test_table_update"

    @pytest.mark.asyncio
    async def test_default_on_delete_emits(self, handler):
        row = FakeRow(id="1")
        await handler.on_delete(row)
        call_args = handler.socketio_server.emit.call_args
        assert call_args[0][0] == "test_table_delete"


@pytest.mark.asyncio
async def test_emit_when_room_is_none_is_skipped(caplog):
    """Regression: emit() must refuse to send with room=None on the
    administrators namespace — socket.io would otherwise broadcast the
    event to every admin regardless of scope."""
    sio = AsyncMock()
    handler = BaseHandler(sio, table="media")

    with caplog.at_level("WARNING"):
        await handler.emit("media_add", "{}", namespace="/administrators", room=None)

    sio.emit.assert_not_called()
    assert any("room=none" in rec.message.lower() for rec in caplog.records)


@pytest.mark.asyncio
async def test_emit_with_room_proceeds():
    sio = AsyncMock()
    handler = BaseHandler(sio, table="media")
    await handler.emit("media_add", "{}", namespace="/administrators", room="cat-a")
    sio.emit.assert_awaited_once_with(
        "media_add", "{}", namespace="/administrators", room="cat-a"
    )


@pytest.mark.asyncio
async def test_emit_room_none_on_userspace_also_skipped():
    """Same guard applies to /userspace — a missing owner/user must not
    broadcast a per-user event to every connected user."""
    sio = AsyncMock()
    handler = BaseHandler(sio, table="media")
    await handler.emit("media_add", "{}", namespace="/userspace", room=None)
    sio.emit.assert_not_called()
