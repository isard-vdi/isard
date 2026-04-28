# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


def _plan(**overrides):
    base = dict(
        id="p1",
        user_id="u1",
        start=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
        end=datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return FakeRow(**base)


class TestResourcePlannerHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.resource_planner import (
            ResourcePlannerHandler,
        )

        sio = AsyncMock()
        # Production instantiates this handler with table="plannings" — see
        # component/change-handler/src/__main__.py.
        return ResourcePlannerHandler(sio, "plannings")

    @pytest.mark.asyncio
    async def test_insert_emits_plan_add_then_admins_event(self, handler):
        await handler.on_insert(_plan())
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        user_args, user_kw = calls[0]
        assert user_args[0] == "plan_add"
        assert user_kw["room"] == "u1"
        assert user_kw["namespace"] == "/userspace"
        admin_args = calls[1][0]
        assert admin_args[0] == "plannings_add"

    @pytest.mark.asyncio
    async def test_insert_formats_start_end_to_string(self, handler):
        await handler.on_insert(_plan())
        user_payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        # _parse_start_end_data uses strftime("%Y-%m-%dT%H:%M%z") — no seconds,
        # tz appended
        assert user_payload["start"].startswith("2026-01-15T09:00")
        assert user_payload["end"].startswith("2026-01-15T10:00")

    @pytest.mark.asyncio
    async def test_update_emits_plan_update_and_admin_event(self, handler):
        await handler.on_update(_plan(), _plan())
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "plan_update"
        assert calls[1][0][0] == "plannings_update"

    @pytest.mark.asyncio
    async def test_delete_emits_plan_delete_and_admin_event(self, handler):
        await handler.on_delete(_plan())
        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "plan_delete"
        assert calls[1][0][0] == "plannings_delete"

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_user_id_is_none(self, handler):
        """Regression: user_id=None must NOT broadcast to whole /userspace."""
        await handler.on_insert(_plan(user_id=None))
        for c in handler.socketio_server.emit.await_args_list:
            room = (
                c.kwargs.get("room")
                if "room" in c.kwargs
                else (c.args[3] if len(c.args) >= 4 else None)
            )
            assert room is not None
