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

from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.helpers.socketio import SocketIO
from socketio import ASGIApp, AsyncRedisManager, AsyncServer

async_server_kwargs = {}
if environ.get("LOG_LEVEL") == "DEBUG":
    kwargs = {"logger": True, "engineio_logger": True}
manager = AsyncRedisManager(socketio_url())
cors_origins = environ.get("CORS_ALLOWED_ORIGINS", "").strip()
cors_allowed = cors_origins.split(",") if cors_origins else []

socketio_server = AsyncServer(
    client_manager=manager,
    async_mode="asgi",
    cors_allowed_origins=cors_allowed if cors_allowed else [],
    **async_server_kwargs,
)
app = ASGIApp(socketio_server, socketio_path="/socket.io")


@socketio_server.event(namespace="*")
async def connect(namespace, sid, environ, auth):
    return await SocketIO(socketio_server, sid).users_connect(auth, namespace)


@socketio_server.event(namespace="*")
async def disconnect(namespace, sid, reason):
    return await SocketIO(socketio_server, sid).quit_users_rooms(None, namespace)


@socketio_server.on("*", namespace="/userspace")
async def event(sid, data):
    print(sid, data)


@socketio_server.on("*", namespace="/administrators")
async def event(sid, data):
    print(sid, data)
