# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestHypervisorsHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.hypervisors import HypervisorsHandler

        sio = AsyncMock()
        return HypervisorsHandler(sio, "hypervisors")

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.count_started_desktops",
        return_value=5,
    )
    async def test_on_insert_fetches_hypervisor(self, mock_count, handler):
        row = FakeRow(id="h1")
        await handler.on_insert(row)

        # count_started_desktops is called with the id from the pinned fetched hypervisor.
        mock_count.assert_called_once_with("h-default")

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["desktops_started"] == 5

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.count_started_desktops",
        return_value=3,
    )
    async def test_on_update_same_status_enriches_model(self, mock_count, handler):
        old = FakeRow(id="h1", status="Online")
        new = FakeRow(id="h1", status="Online")
        await handler.on_update(old, new)

        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["desktops_started"] == 3

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.get_hypervisor",
        return_value={"id": "h1", "status": "Offline"},
    )
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.count_started_desktops",
        return_value=0,
    )
    async def test_on_update_status_change_fetches_hypervisor(
        self, mock_count, mock_get, handler
    ):
        old = FakeRow(id="h1", status="Online")
        new = FakeRow(id="h1", status="Offline")
        await handler.on_update(old, new)

        mock_get.assert_called_once_with("h1")
        assert handler.socketio_server.emit.await_count == 1

    @pytest.mark.asyncio
    @patch("isardvdi_change_handler.handlers.hypervisors.Hypervisor.get_hypervisor")
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.count_started_desktops",
        return_value=7,
    )
    async def test_on_update_online_same_status_no_refetch(
        self, mock_count, mock_get, handler
    ):
        """Same-status Online path: DB row is not re-fetched; count is called."""
        old = FakeRow(id="h1", status="Online")
        new = FakeRow(id="h1", status="Online", name="host-new")
        await handler.on_update(old, new)

        mock_get.assert_not_called()
        mock_count.assert_called_once_with("h1")
        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["name"] == "host-new"
        assert payload["desktops_started"] == 7

    @pytest.mark.asyncio
    @patch("isardvdi_change_handler.handlers.hypervisors.Hypervisor.get_hypervisor")
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.count_started_desktops"
    )
    async def test_on_update_offline_same_status_forces_zero(
        self, mock_count, mock_get, handler
    ):
        """Offline same-status path: count_started_desktops is NOT called —
        desktops_started is forced to 0 directly. This pins an important
        business rule the handler has relied on for a long time.
        """
        old = FakeRow(id="h1", status="Offline")
        new = FakeRow(id="h1", status="Offline")
        await handler.on_update(old, new)

        mock_get.assert_not_called()
        mock_count.assert_not_called()
        payload = json.loads(handler.socketio_server.emit.call_args[0][1])
        assert payload["desktops_started"] == 0

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.get_hypervisor",
        return_value=None,
    )
    async def test_on_insert_skips_when_hypervisor_missing(self, mock_get, handler):
        row = FakeRow(id="h1")
        await handler.on_insert(row)
        handler.socketio_server.emit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_delete_emits_old_val(self, handler):
        row = FakeRow(id="h1", status="Offline")
        await handler.on_delete(row)

        call = handler.socketio_server.emit.call_args
        assert call[0][0] == "hyper_deleted"
        # Admin-only emission: verify namespace + room explicitly.
        assert call.kwargs["namespace"] == "/administrators"
        assert call.kwargs["room"] == "admins"
