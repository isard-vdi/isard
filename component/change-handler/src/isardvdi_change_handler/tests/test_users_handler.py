# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


def _tuples(handler):
    """Extract (event, payload_dict, namespace, room) per emit call."""
    result = []
    for call in handler.socketio_server.emit.call_args_list:
        args, kwargs = call
        event = args[0]
        payload = json.loads(args[1])
        namespace = args[2] if len(args) > 2 else kwargs.get("namespace")
        room = args[3] if len(args) > 3 else kwargs.get("room")
        result.append((event, payload, namespace, room))
    return result


class TestUsersHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.users import UsersHandler

        sio = AsyncMock()
        return UsersHandler(sio, "users")

    @pytest.mark.asyncio
    async def test_on_insert_enriches_with_role_and_group(self, handler):
        row = FakeRow(id="u1", name="Alice", category="cat1")
        await handler.on_insert(row)

        assert handler.socketio_server.emit.await_count == 3

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["id"] == "u1"
        assert payload["role_name"] == "user"
        assert payload["group_name"] == "G1"

    @pytest.mark.asyncio
    async def test_on_insert_emits_users_data_to_user_admins_and_category_rooms(
        self, handler
    ):
        """Pin full (event, namespace, room) contract for all 3 insert emits."""
        row = FakeRow(id="u1", name="Alice", category="cat1")
        await handler.on_insert(row)

        tuples = _tuples(handler)
        assert all(e == "users_data" for e, _, _, _ in tuples)
        targets = {(ns, room) for _, _, ns, room in tuples}
        assert ("/userspace", "u1") in targets
        assert ("/administrators", "admins") in targets
        assert ("/administrators", "cat1") in targets
        # Enrichment merged on every emitted payload, not just the first.
        for _, payload, _, _ in tuples:
            assert payload["role_name"] == "user"
            assert payload["group_name"] == "G1"
            assert payload["category_name"] == "Cat"

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.lib.users.users.user.UsersProcessed.get_user_role_group_and_category_name",
        return_value={"role_name": "Admin", "group_name": "G", "category_name": "Cat"},
    )
    async def test_on_update_enrichment_overwrites_role_name(self, _mock, handler):
        """Even if new_val already carries a role_name, the fresh DB value wins.
        Contract: enrichment merges AFTER the model's own additional_properties.
        """
        old = FakeRow(id="u1", category="cat1")
        new = FakeRow(
            id="u1",
            category="cat1",
            additional_properties={"role_name": "user"},
        )
        await handler.on_update(old, new)

        for _, payload, _, _ in _tuples(handler):
            assert payload["role_name"] == "Admin"

    @pytest.mark.asyncio
    async def test_on_update_emits_to_correct_rooms(self, handler):
        old = FakeRow(id="u1", category="cat1")
        new = FakeRow(id="u1", name="Bob", category="cat1")
        await handler.on_update(old, new)

        rooms = [
            call[1]["room"] for call in handler.socketio_server.emit.call_args_list
        ]
        assert "u1" in rooms
        assert "admins" in rooms
        assert "cat1" in rooms

    @pytest.mark.asyncio
    async def test_on_delete_emits_users_delete_to_same_rooms(self, handler):
        row = FakeRow(id="u1", category="cat1")
        await handler.on_delete(row)

        tuples = _tuples(handler)
        assert all(e == "users_delete" for e, _, _, _ in tuples)
        targets = {(ns, room) for _, _, ns, room in tuples}
        assert ("/userspace", "u1") in targets
        assert ("/administrators", "admins") in targets
        assert ("/administrators", "cat1") in targets

    @pytest.mark.asyncio
    async def test_on_delete_uses_attribute_access(self, handler):
        row = FakeRow(id="u1", category="cat1")
        await handler.on_delete(row)

        rooms = [
            call[1]["room"] for call in handler.socketio_server.emit.call_args_list
        ]
        assert "u1" in rooms
        assert "admins" in rooms
        assert "cat1" in rooms


class TestUsersHandlerNoneRoomRegression:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.users import UsersHandler

        sio = AsyncMock()
        return UsersHandler(sio, "users")

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.lib.users.users.user.UsersProcessed.get_user_role_group_and_category_name",
        return_value={"role_name": "user", "group_name": "G", "category_name": "Cat"},
    )
    async def test_on_insert_skips_when_category_is_none(self, _mock, handler):
        """Regression: category=None must NOT broadcast to whole /administrators."""
        row = FakeRow(id="u1", name="Alice", category=None)
        await handler.on_insert(row)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.lib.users.users.user.UsersProcessed.get_user_role_group_and_category_name",
        return_value={"role_name": "user", "group_name": "G", "category_name": "Cat"},
    )
    async def test_on_update_skips_when_category_is_none(self, _mock, handler):
        old = FakeRow(id="u1", category="cat1")
        new = FakeRow(id="u1", name="Bob", category=None)
        await handler.on_update(old, new)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []

    @pytest.mark.asyncio
    async def test_on_delete_skips_when_category_is_none(self, handler):
        row = FakeRow(id="u1", category=None)
        await handler.on_delete(row)
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []
