# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for isardvdi_common.helpers.socketio.SocketIO — the real logic
behind the thin `component/socketio/` service module.

What this class owns:
- `users_connect(auth, namespace)` — decodes the JWT from the auth dict
  and puts the sid into the right SocketIO room based on payload
  fields. This is THE admin-vs-user isolation boundary: admin joins
  "admins", manager joins their category room, user/advanced just
  land in their user_id room. A desktop_id JWT (direct-viewer tokens)
  joins only the desktop room.
- `quit_users_rooms(jwt, namespace)` — leaves whichever room was
  joined on connect, tolerant to expired/bad tokens.
"""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.helpers.socketio import SocketIO


def _make(sio=None):
    """Construct a SocketIO helper with a mocked async socket."""
    if sio is None:
        sio = MagicMock()
        sio.enter_room = MagicMock()
        sio.leave_room = MagicMock()
    return SocketIO(sio, sid="sid-1")


# -------------------------------------------------------------------------
# users_connect — authentication + room entry
# -------------------------------------------------------------------------


class TestUsersConnectAuthGuards:
    @pytest.mark.asyncio
    async def test_none_auth_returns_false(self):
        h = _make()
        result = await h.users_connect(None, "/userspace")
        assert result is False
        h.socketio.enter_room.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        side_effect=Exception("bad jwt"),
    )
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_expired_user_data",
        return_value=None,
    )
    async def test_bad_jwt_returns_false_and_attempts_quit(
        self, _mock_expired, _mock_payload
    ):
        h = _make()
        result = await h.users_connect({"jwt": "garbage"}, "/userspace")
        assert result is False
        h.socketio.enter_room.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u1",
            "category_id": "default",
            "role_id": "ghost",
        },
    )
    async def test_unknown_role_returns_false(self, _mock):
        h = _make()
        result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is False


# -------------------------------------------------------------------------
# Direct-viewer desktop_id token — enter desktop room only
# -------------------------------------------------------------------------


class _FakeRdbContext(contextlib.AbstractContextManager):
    """Replace the class-level RethinkDB context manager with a no-op so
    tests don't try to dial a real DB."""

    def __exit__(self, *a):
        return False


class TestUsersConnectDesktopToken:
    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.r.table",
        return_value=MagicMock(
            get=MagicMock(
                return_value=MagicMock(run=MagicMock(return_value={"id": "d1"}))
            )
        ),
    )
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={"desktop_id": "d1"},
    )
    async def test_valid_desktop_token_enters_desktop_room(
        self, _mock_payload, _mock_r
    ):
        h = _make()
        with patch.object(type(h), "_rdb_context", _FakeRdbContext):
            result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is True
        h.socketio.enter_room.assert_called_once_with(
            "sid-1", "d1", namespace="/userspace"
        )

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.r.table",
        return_value=MagicMock(
            get=MagicMock(return_value=MagicMock(run=MagicMock(return_value=None)))
        ),
    )
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={"desktop_id": "missing-desk"},
    )
    async def test_desktop_not_in_db_returns_false(self, _mock_payload, _mock_r):
        h = _make()
        with patch.object(type(h), "_rdb_context", _FakeRdbContext):
            result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is False
        h.socketio.enter_room.assert_not_called()


# -------------------------------------------------------------------------
# Role-based room routing — the admin/user isolation boundary
# -------------------------------------------------------------------------


class TestUsersConnectRoleRouting:
    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u1",
            "category_id": "default",
            "role_id": "user",
        },
    )
    async def test_plain_user_enters_user_id_room_only(self, _mock):
        h = _make()
        result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is True
        # Exactly one enter_room call, on the user's own room.
        assert h.socketio.enter_room.call_count == 1
        h.socketio.enter_room.assert_called_once_with(
            "sid-1", "u1", namespace="/userspace"
        )

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u1",
            "category_id": "default",
            "role_id": "advanced",
        },
    )
    async def test_advanced_user_same_as_plain_user(self, _mock):
        h = _make()
        result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is True
        assert h.socketio.enter_room.call_count == 1

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u-admin",
            "category_id": "default",
            "role_id": "admin",
        },
    )
    async def test_admin_enters_user_room_AND_admins_room(self, _mock):
        h = _make()
        result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is True
        rooms = [c.args[1] for c in h.socketio.enter_room.call_args_list]
        # Admin gets both their personal user_id room AND the global admins room.
        assert "u-admin" in rooms
        assert "admins" in rooms

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u-mgr",
            "category_id": "cat-mgr",
            "role_id": "manager",
        },
    )
    async def test_manager_enters_user_room_AND_category_room(self, _mock):
        h = _make()
        result = await h.users_connect({"jwt": "ok"}, "/userspace")
        assert result is True
        rooms = [c.args[1] for c in h.socketio.enter_room.call_args_list]
        # Manager gets their personal user_id room AND a category-scoped room
        # — but NOT the global "admins" room (the isolation boundary).
        assert "u-mgr" in rooms
        assert "cat-mgr" in rooms
        assert "admins" not in rooms

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={
            "user_id": "u1",
            "category_id": "default",
            "role_id": "user",
        },
    )
    async def test_namespace_is_forwarded_verbatim(self, _mock):
        h = _make()
        await h.users_connect({"jwt": "ok"}, "/administrators")
        kwargs = h.socketio.enter_room.call_args.kwargs
        assert kwargs["namespace"] == "/administrators"


# -------------------------------------------------------------------------
# quit_users_rooms — leave whichever room was entered
# -------------------------------------------------------------------------


class TestQuitUsersRooms:
    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={"user_id": "u1", "role_id": "user"},
    )
    async def test_leaves_user_room_on_normal_quit(self, _mock):
        h = _make()
        payload = await h.quit_users_rooms("jwt", "/userspace")
        h.socketio.leave_room.assert_called_once_with(
            "sid-1", "u1", namespace="/userspace"
        )
        assert payload["user_id"] == "u1"

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        return_value={"desktop_id": "d1"},
    )
    async def test_leaves_desktop_room_when_desktop_token(self, _mock):
        h = _make()
        await h.quit_users_rooms("jwt", "/userspace")
        h.socketio.leave_room.assert_called_once_with(
            "sid-1", "d1", namespace="/userspace"
        )

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_expired_user_data",
        return_value=None,
    )
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_token_payload",
        side_effect=Exception("bad token"),
    )
    async def test_bad_token_with_no_expired_data_returns_empty(
        self, _mock_payload, _mock_expired
    ):
        h = _make()
        result = await h.quit_users_rooms("garbage", "/userspace")
        assert result == {}
        h.socketio.leave_room.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "isardvdi_common.helpers.socketio.Token.get_expired_user_data",
        return_value={"user_id": "u-expired", "role_id": "user"},
    )
    @patch(
        "isardvdi_common.helpers.socketio.ExpiredSignatureError",
        new=type("ExpiredSignatureError", (Exception,), {}),
    )
    async def test_expired_token_falls_back_to_expired_user_data(self, _mock_expired):
        """When the JWT is expired, quit_users_rooms must still leave the
        user's room — otherwise disconnecting a session with an expired
        token leaves stale subscriptions behind."""
        h = _make()
        # Raise the same ExpiredSignatureError subclass the real code catches.
        from isardvdi_common.helpers import socketio as socketio_mod

        with patch.object(
            socketio_mod.Token,
            "get_token_payload",
            side_effect=socketio_mod.ExpiredSignatureError("expired"),
        ):
            payload = await h.quit_users_rooms("expired-jwt", "/userspace")
        h.socketio.leave_room.assert_called_once_with(
            "sid-1", "u-expired", namespace="/userspace"
        )
        assert payload["user_id"] == "u-expired"
