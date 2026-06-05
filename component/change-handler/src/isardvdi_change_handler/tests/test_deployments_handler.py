# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestDeploymentsHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.deployments import DeploymentsHandler

        sio = AsyncMock()
        return DeploymentsHandler(sio, "deployments")

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.deployments.Deployment.get",
        return_value={"id": "d1", "user": "u1", "name": "Deploy"},
    )
    async def test_insert_emits_deployment_add_to_user_and_admin_fallback(
        self, _mock_get, handler
    ):
        await handler.on_insert(FakeRow(id="d1", user="u1"))
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        user_args, user_kwargs = calls[0]
        assert user_args[0] == "deployment_add"
        assert user_kwargs["namespace"] == "/userspace"
        assert user_kwargs["room"] == "u1"
        # Second emit comes from BaseHandler.on_insert. BaseHandler.emit
        # passes namespace/room as kwargs.
        admin_args, admin_kwargs = calls[1]
        assert admin_args[0] == "deployments_add"
        assert admin_kwargs["namespace"] == "/administrators"
        assert admin_kwargs["room"] == "admins"

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.deployments.DeploymentsProcessed.get_deployment_or_none",
        return_value={"id": "d1", "user": "u1", "co_owners": ["u2"], "name": "New"},
    )
    async def test_update_emits_deployment_update_to_owner(self, _mock_get, handler):
        old = FakeRow(id="d1", user="u1", name="Old")
        new = FakeRow(id="d1", user="u1", name="New")
        await handler.on_update(old, new)
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 3
        user_args, user_kwargs = calls[0]
        assert user_args[0] == "deployment_update"
        assert user_kwargs["room"] == "u1"
        payload = json.loads(user_args[1])
        assert payload["name"] == "New"
        # List event (plural) must reach the user's deployments list on
        # /userspace, with co-owners included in the room.
        list_args, list_kwargs = calls[1]
        assert list_args[0] == "deployments_update"
        assert list_kwargs["namespace"] == "/userspace"
        assert list_kwargs["room"] == ["u2", "u1"]
        admin_args = calls[2][0]
        assert admin_args[0] == "deployments_update"

    @pytest.mark.asyncio
    async def test_delete_emits_deployment_delete_with_id_to_user(self, handler):
        await handler.on_delete(FakeRow(id="d1", user="u1", name="Deploy"))
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        user_args, user_kwargs = calls[0]
        assert user_args[0] == "deployment_delete"
        assert user_kwargs["room"] == "u1"
        payload = json.loads(user_args[1])
        assert payload == {"id": "d1"}
        admin_args = calls[1][0]
        assert admin_args[0] == "deployments_delete"


class TestDeploymentsRegression:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.deployments import DeploymentsHandler

        sio = AsyncMock()
        return DeploymentsHandler(sio, "deployments")

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.deployments.Deployment.get",
        return_value={"id": "d1", "user": None, "name": "Deploy"},
    )
    async def test_on_insert_skips_when_user_is_none(self, _mock_get, handler):
        """Regression: user=None must NOT broadcast to whole /userspace."""
        await handler.on_insert(FakeRow(id="d1", user=None))
        for c in handler.socketio_server.emit.await_args_list:
            room = (
                c.kwargs.get("room")
                if "room" in c.kwargs
                else (c.args[3] if len(c.args) >= 4 else None)
            )
            assert room is not None
