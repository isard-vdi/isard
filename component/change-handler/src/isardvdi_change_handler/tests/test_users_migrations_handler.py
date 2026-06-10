# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

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


class TestUsersMigrationsHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.users_migrations import (
            UsersMigrationsHandler,
        )

        sio = AsyncMock()
        return UsersMigrationsHandler(sio, "users_migrations")

    @pytest.mark.asyncio
    async def test_on_update_emits_progress_to_target_user_and_admins(self, handler):
        row = FakeRow(
            id="m1",
            additional_properties={
                "origin_user": "old",
                "target_user": "new",
                "status": "migrating",
                "migrated_desktops": True,
            },
        )
        await handler.on_update(row, row)

        tuples = _tuples(handler)
        targets = {(e, ns, room) for e, _, ns, room in tuples}
        # User-facing progress event to the importing user's own room.
        assert ("user_migration_data", "/userspace", "new") in targets
        # Admin datatable refresh preserved.
        assert ("users_migrations_update", "/administrators", "admins") in targets
        # Progress payload carries the unwrapped record fields.
        progress = next(p for e, p, _, _ in tuples if e == "user_migration_data")
        assert progress["status"] == "migrating"
        assert progress["migrated_desktops"] is True

    @pytest.mark.asyncio
    async def test_on_insert_emits_progress(self, handler):
        row = FakeRow(
            id="m1",
            additional_properties={"target_user": "new", "status": "migrating"},
        )
        await handler.on_insert(row)

        tuples = _tuples(handler)
        targets = {(e, ns, room) for e, _, ns, room in tuples}
        assert ("user_migration_data", "/userspace", "new") in targets
        assert ("users_migrations_add", "/administrators", "admins") in targets

    @pytest.mark.asyncio
    async def test_skips_userspace_emit_without_target_user(self, handler):
        row = FakeRow(id="m1", additional_properties={"status": "exported"})
        await handler.on_update(row, row)

        events = {e for e, _, _, _ in _tuples(handler)}
        # No user-facing emit when target_user is unknown, but admins still notified.
        assert "user_migration_data" not in events
        assert "users_migrations_update" in events
