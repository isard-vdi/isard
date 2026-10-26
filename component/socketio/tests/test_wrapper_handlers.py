import asyncio
from unittest import mock

import pytest
from isardvdi_socketio.connected import Presence
from tests.fake_redis import FakeRedis


def test_connect_delegates_to_users_connect(pristine_module, monkeypatch):
    monkeypatch.setattr(pristine_module, "presence", Presence(FakeRedis()))
    fake_socketio = mock.MagicMock()
    fake_socketio.return_value.users_connect = mock.AsyncMock(return_value="joined")
    monkeypatch.setattr(pristine_module, "SocketIO", fake_socketio)

    result = asyncio.run(
        pristine_module.connect("/userspace", "sid-1", {"HTTP_HOST": "x"}, {"jwt": "t"})
    )

    assert result == "joined"
    fake_socketio.assert_called_once_with(pristine_module.socketio_server, "sid-1")
    fake_socketio.return_value.users_connect.assert_awaited_once_with(
        {"jwt": "t"}, "/userspace"
    )


def test_disconnect_delegates_to_quit_users_rooms(pristine_module, monkeypatch):
    monkeypatch.setattr(pristine_module, "presence", Presence(FakeRedis()))
    fake_socketio = mock.MagicMock()
    fake_socketio.return_value.quit_users_rooms = mock.AsyncMock(return_value="left")
    monkeypatch.setattr(pristine_module, "SocketIO", fake_socketio)

    result = asyncio.run(
        pristine_module.disconnect("/administrators", "sid-2", "transport close")
    )

    assert result == "left"
    fake_socketio.assert_called_once_with(pristine_module.socketio_server, "sid-2")
    fake_socketio.return_value.quit_users_rooms.assert_awaited_once_with(
        None, "/administrators"
    )


@pytest.mark.parametrize("namespace", ["/userspace", "/administrators"])
def test_unhandled_event_is_dispatched_without_error(pristine_module, namespace):
    server = pristine_module.socketio_server
    asyncio.run(
        server._trigger_event("no-such-event", namespace, "sid-3", {"payload": 1})
    )
