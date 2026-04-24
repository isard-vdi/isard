# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.conftest import FakeRow

COUNT_PAYLOAD = {
    "id": "rb1",
    "desktops": 0,
    "templates": 0,
    "storages": 1,
    "deployments": 0,
    "categories": 0,
    "groups": 0,
    "users": 0,
    "last": None,
}


def _patch_helpers(count_payload=None, user_amount=3):
    payload = count_payload if count_payload is not None else dict(COUNT_PAYLOAD)
    return patch.multiple(
        "handlers.recycle_bin.RecycleBinHelpers",
        get_count=MagicMock(return_value=payload),
        get_user_amount=MagicMock(return_value=user_amount),
    )


class TestRecycleBinHandlerProp:
    """Tests for the _prop helper that reads model attributes or additional_properties."""

    @pytest.fixture
    def handler(self):
        from handlers.recycle_bin import RecycleBinHandler

        sio = AsyncMock()
        return RecycleBinHandler(sio, "recycle_bin")

    def test_prop_returns_declared_model_attribute(self, handler):
        # id is a declared FakeRow field — found via getattr
        row = FakeRow(id="rb-1", status="pending")
        assert handler._prop(row, "id") == "rb-1"

    def test_prop_falls_back_to_additional_properties(self, handler):
        # owner_id is NOT a declared FakeRow field — falls back to additional_properties
        row = FakeRow(additional_properties={"owner_id": "user-1"})
        assert handler._prop(row, "owner_id") == "user-1"

    def test_prop_returns_default_when_key_missing_entirely(self, handler):
        row = FakeRow()
        assert handler._prop(row, "owner_id", "fallback") == "fallback"

    def test_prop_returns_none_when_key_missing_and_no_default(self, handler):
        row = FakeRow()
        assert handler._prop(row, "owner_id") is None


class TestRecycleBinHandler:
    @pytest.fixture
    def handler(self):
        from handlers.recycle_bin import RecycleBinHandler

        sio = AsyncMock()
        return RecycleBinHandler(sio, "recycle_bin")

    # ---------------------------------------------------------------- on_insert

    @pytest.mark.asyncio
    async def test_insert_without_owner_id_skips(self, handler):
        # owner_id not present → _prop returns None → handler returns early
        row = FakeRow(id="rb1", status="recycled")
        await handler.on_insert(row)
        assert handler.socketio_server.emit.await_args_list == []

    @pytest.mark.asyncio
    async def test_insert_with_owner_emits_add_to_user_and_admins(self, handler):
        # owner_id in additional_properties; id and status on the model directly
        row = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        with _patch_helpers():
            await handler.on_insert(row)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == ["add_recycle_bin", "add_recycle_bin"]
        assert calls[0].kwargs == {"namespace": "/userspace", "room": "u1"}
        assert calls[1].kwargs == {"namespace": "/administrators", "room": "admins"}
        payload = json.loads(calls[0].args[1])
        assert payload["id"] == "rb1"
        assert payload["items_in_bin"] == 3

    # ---------------------------------------------------------------- on_update

    @pytest.mark.asyncio
    async def test_update_without_owner_skips(self, handler):
        old = FakeRow(id="rb1", status="recycled")
        new = FakeRow(id="rb1", status="recycled")
        await handler.on_update(old, new)
        assert handler.socketio_server.emit.await_args_list == []

    @pytest.mark.asyncio
    async def test_update_first_owner_emits_add(self, handler):
        # old has no owner_id, new does → treated as first appearance
        old = FakeRow(id="rb1", status="recycled")
        new = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        with _patch_helpers():
            await handler.on_update(old, new)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == ["add_recycle_bin", "add_recycle_bin"]
        assert calls[0].kwargs["room"] == "u1"
        assert calls[1].kwargs["room"] == "admins"

    @pytest.mark.asyncio
    async def test_update_status_to_deleted_emits_delete(self, handler):
        old = FakeRow(
            id="rb1",
            status="deleting",
            additional_properties={"owner_id": "u1"},
        )
        new = FakeRow(
            id="rb1",
            status="deleted",
            additional_properties={"owner_id": "u1"},
        )
        await handler.on_update(old, new)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == [
            "delete_recycle_bin",
            "delete_recycle_bin",
        ]
        payload = json.loads(calls[0].args[1])
        assert payload == {"id": "rb1", "status": "deleted"}

    @pytest.mark.asyncio
    async def test_update_status_other_emits_update_with_status(self, handler):
        old = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        new = FakeRow(
            id="rb1",
            status="deleting",
            additional_properties={"owner_id": "u1"},
        )
        await handler.on_update(old, new)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == [
            "update_recycle_bin",
            "update_recycle_bin",
        ]
        payload = json.loads(calls[0].args[1])
        assert payload == {"id": "rb1", "status": "deleting"}

    @pytest.mark.asyncio
    async def test_update_no_status_change_emits_count_payload(self, handler):
        old = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        new = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        with _patch_helpers():
            await handler.on_update(old, new)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == [
            "update_recycle_bin",
            "update_recycle_bin",
        ]
        payload = json.loads(calls[0].args[1])
        assert payload["id"] == "rb1"
        assert "items_in_bin" not in payload

    # ---------------------------------------------------------------- on_delete

    @pytest.mark.asyncio
    async def test_delete_emits_delete_with_status_from_old_val(self, handler):
        old = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": "u1"},
        )
        await handler.on_delete(old)
        calls = handler.socketio_server.emit.await_args_list
        assert [c.args[0] for c in calls] == [
            "delete_recycle_bin",
            "delete_recycle_bin",
        ]
        payload = json.loads(calls[0].args[1])
        assert payload == {"id": "rb1", "status": "recycled"}

    @pytest.mark.asyncio
    async def test_delete_without_owner_skips(self, handler):
        old = FakeRow(id="rb1", status="recycled")
        await handler.on_delete(old)
        assert handler.socketio_server.emit.await_args_list == []


class TestRecycleBinHandlerNoneRoomRegression:
    @pytest.fixture
    def handler(self):
        from handlers.recycle_bin import RecycleBinHandler

        sio = AsyncMock()
        return RecycleBinHandler(sio, "recycle_bin")

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_owner_id_is_none(self, handler):
        """Regression: owner_id=None must NOT broadcast to whole /userspace."""
        row = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": None},
        )
        with _patch_helpers():
            await handler.on_insert(row)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []

    @pytest.mark.asyncio
    async def test_on_update_skips_when_owner_id_is_none(self, handler):
        old = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": None},
        )
        new = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": None},
        )
        with _patch_helpers():
            await handler.on_update(old, new)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []

    @pytest.mark.asyncio
    async def test_on_delete_skips_when_owner_id_is_none(self, handler):
        row = FakeRow(
            id="rb1",
            status="recycled",
            additional_properties={"owner_id": None},
        )
        await handler.on_delete(row)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []
