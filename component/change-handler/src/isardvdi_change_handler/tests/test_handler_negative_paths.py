# SPDX-License-Identifier: AGPL-3.0-or-later

"""Defensive-contract tests for change-handler handlers.

`BaseHandler.handle()` wraps every dispatch in a try/except, logs, and
swallows exceptions so a single malformed change payload doesn't kill
the Redis-stream consumer feeding every handler. These tests pin that
contract:

- An exception raised from a handler's `on_insert` / `on_update` /
  `on_delete` must NOT escape `handle()` — the consumer keeps running.
- Optional-key tolerance for handlers that branch on missing attributes
  (e.g. groups without parent_category, hypervisors missing a DB row).

The legacy REQUIRED_KEYS short-circuit is gone: handlers now receive
Pydantic models whose missing fields default to None, so the old
"missing key skips emit" contract is no longer expressible (the emit
goes out with room=None). This file no longer pins that behaviour.
"""

from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeChange, FakeRow


def _sio():
    return AsyncMock()


def _insert_change(**fields):
    return FakeChange(new_val=FakeRow(**fields), old_val=None)


def _delete_change(**fields):
    return FakeChange(new_val=None, old_val=FakeRow(**fields))


class TestOptionalKeyTolerance:
    """Handlers that defensively branch on missing keys must NOT raise."""

    @pytest.mark.asyncio
    async def test_groups_insert_without_parent_category_succeeds(self):
        from isardvdi_change_handler.handlers.groups import GroupsHandler

        handler = GroupsHandler(_sio(), "groups")
        await handler.handle(_insert_change(id="g1", name="Devs"))
        # 2 emits (userspace + admins), no third per-category emit.
        assert handler.socketio_server.emit.await_count == 2

    @pytest.mark.asyncio
    async def test_vgpus_insert_without_mdevs_returns_empty_started(self):
        from isardvdi_change_handler.handlers.vgpus import VgpusHandler

        handler = VgpusHandler(_sio(), "vgpus")
        await handler.handle(
            _insert_change(
                additional_properties={"id": "g1", "vgpu_profile": None, "mdevs": {}}
            )
        )
        # The single vgpu_data emit goes out; desktops_started defaults to [].
        assert handler.socketio_server.emit.await_count == 1

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.hypervisors.Hypervisor.get_hypervisor",
        side_effect=Exception("not found"),
    )
    async def test_hypervisors_insert_swallows_missing_row(self, _mock_get):
        """DB raises → handle()'s try/except keeps the consumer alive
        and prevents any partial emit.
        """
        from isardvdi_change_handler.handlers.hypervisors import HypervisorsHandler

        handler = HypervisorsHandler(_sio(), "hypervisors")
        await handler.handle(_insert_change(id="h1"))
        handler.socketio_server.emit.assert_not_awaited()


class TestHandleSwallowsAnyHandlerException:
    """Belt-and-braces: an arbitrary RuntimeError raised from the
    overridden on_insert/on_update/on_delete must not escape handle().
    """

    @pytest.mark.asyncio
    async def test_on_insert_runtime_error_is_swallowed(self):
        from isardvdi_change_handler.handlers.base import BaseHandler

        handler = BaseHandler(_sio(), "anything")
        handler.on_insert = AsyncMock(side_effect=RuntimeError("boom"))
        await handler.handle(_insert_change(id="x"))  # must not raise

    @pytest.mark.asyncio
    async def test_on_update_runtime_error_is_swallowed(self):
        from isardvdi_change_handler.handlers.base import BaseHandler

        handler = BaseHandler(_sio(), "anything")
        handler.on_update = AsyncMock(side_effect=RuntimeError("boom"))
        await handler.handle(
            FakeChange(old_val=FakeRow(id="x"), new_val=FakeRow(id="x"))
        )

    @pytest.mark.asyncio
    async def test_on_delete_runtime_error_is_swallowed(self):
        from isardvdi_change_handler.handlers.base import BaseHandler

        handler = BaseHandler(_sio(), "anything")
        handler.on_delete = AsyncMock(side_effect=RuntimeError("boom"))
        await handler.handle(_delete_change(id="x"))
