#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import logging
from os import environ

import isardvdi_common.helpers.log  # noqa: F401  installs the JSON root handler
import redis.asyncio as aioredis
from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.helpers.socketio import SocketIO
from isardvdi_common.helpers.token import Token
from isardvdi_socketio.connected import Presence
from socketio import ASGIApp, AsyncRedisManager, AsyncServer

log = logging.getLogger(__name__)

SOCKETIO_DEBUG_MODES = {
    "app": (),
    "socketio": ("socketio.server",),
    "all": ("socketio.server", "engineio.server"),
}


def debug_server_kwargs(mode):
    mode = (mode or "").strip().lower()
    if mode not in SOCKETIO_DEBUG_MODES and mode not in ("", "off", "false", "no"):
        log.warning("SOCKETIO_DEBUG=%r is not app, socketio or all; ignored", mode)
    enabled = SOCKETIO_DEBUG_MODES.get(mode)
    log.setLevel(logging.NOTSET if enabled is None else logging.DEBUG)
    # a Logger, not True: True also adds a plain-text StreamHandler to it
    kwargs = {}
    for kwarg, name in (
        ("logger", "socketio.server"),
        ("engineio_logger", "engineio.server"),
    ):
        library_log = logging.getLogger(name)
        on = name in (enabled or ())
        library_log.setLevel(logging.DEBUG if on else logging.ERROR)
        kwargs[kwarg] = library_log
    return kwargs


async_server_kwargs = debug_server_kwargs(environ.get("SOCKETIO_DEBUG"))
manager = AsyncRedisManager(socketio_url())
cors_origins = environ.get("CORS_ALLOWED_ORIGINS", "")
cors_allowed = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]

socketio_server = AsyncServer(
    client_manager=manager,
    async_mode="asgi",
    cors_allowed_origins=cors_allowed if cors_allowed else [],
    **async_server_kwargs,
)
presence = Presence(
    aioredis.from_url(socketio_url(), decode_responses=True, socket_connect_timeout=5)
)
app = ASGIApp(
    socketio_server,
    socketio_path="/socket.io",
    on_startup=presence.start,
    on_shutdown=presence.stop,
)


def _user_id(auth):
    try:
        return Token.get_token_payload((auth or {}).get("jwt")).get("user_id") or ""
    except Exception:
        return ""


@socketio_server.event(namespace="*")
async def connect(namespace, sid, environ, auth):
    connected = await SocketIO(socketio_server, sid).users_connect(auth, namespace)
    if connected:
        await presence.add(sid, _user_id(auth))
    return connected


@socketio_server.event(namespace="*")
async def disconnect(namespace, sid, reason):
    await presence.remove(sid)
    return await SocketIO(socketio_server, sid).quit_users_rooms(None, namespace)


async def unhandled_event(event, sid, *args):
    log.debug("unhandled socketio event %s from %s", event, sid)


for _namespace in ("/userspace", "/administrators"):
    socketio_server.on("*", namespace=_namespace)(unhandled_event)
