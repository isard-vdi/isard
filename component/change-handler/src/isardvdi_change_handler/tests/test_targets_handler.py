# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestTargetsHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.targets import TargetsHandler

        sio = AsyncMock()
        return TargetsHandler(sio, "targets")

    @pytest.mark.asyncio
    async def test_insert_emits_to_user_then_super_to_admins(self, handler):
        await handler.on_insert(FakeRow(id="t1", user_id="u1", name="bastion-1"))
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        # 1st: user-scoped targets_add (namespace/room as kwargs)
        args0, kw0 = calls[0]
        assert args0[0] == "targets_add"
        assert kw0["namespace"] == "/userspace"
        assert kw0["room"] == "u1"
        # 2nd: admins-scoped targets_add from BaseHandler.on_insert
        # (namespace/room as kwargs via super)
        args1, kw1 = calls[1]
        assert args1[0] == "targets_add"
        assert kw1["namespace"] == "/administrators"
        assert kw1["room"] == "admins"

    @pytest.mark.asyncio
    async def test_update_emits_targets_update_to_user_and_admins(self, handler):
        old = FakeRow(id="t1", user_id="u1", name="old")
        new = FakeRow(id="t1", user_id="u1", name="new")
        await handler.on_update(old, new)
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "targets_update"
        assert calls[1][0][0] == "targets_update"

    @pytest.mark.asyncio
    async def test_delete_emits_targets_delete_with_id_only_to_user(self, handler):
        await handler.on_delete(FakeRow(id="t1", user_id="u1", name="bastion-1"))
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        # User-scoped delete payload is stripped to {"id": ...}
        user_args, user_kwargs = calls[0]
        assert user_args[0] == "targets_delete"
        assert user_kwargs["room"] == "u1"
        payload = json.loads(user_args[1])
        assert payload == {"id": "t1"}
        # Admin-scoped delete from BaseHandler carries full old_val
        admin_args, admin_kwargs = calls[1]
        assert admin_args[0] == "targets_delete"
        assert admin_kwargs["namespace"] == "/administrators"
        assert admin_kwargs["room"] == "admins"
        admin_payload = json.loads(admin_args[1])
        assert admin_payload["name"] == "bastion-1"

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_user_id_is_none(self, handler):
        """Regression: user_id=None must NOT broadcast to whole /userspace."""
        await handler.on_insert(FakeRow(id="t1", user_id=None, name="b"))
        for c in handler.socketio_server.emit.await_args_list:
            room = (
                c.kwargs.get("room")
                if "room" in c.kwargs
                else (c.args[3] if len(c.args) >= 4 else None)
            )
            assert room is not None
