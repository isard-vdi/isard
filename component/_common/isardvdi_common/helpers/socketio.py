#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2017 Josep Maria Viñolas Auquer and Alberto Larraz Dalmases
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
import os
from pprint import pformat

import simple_colors as sc
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.token import Token
from jwt import ExpiredSignatureError
from rethinkdb import r


class SocketIO(RethinkSharedConnection):

    logger = logging

    def __init__(self, socketio, sid, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.socketio = socketio
        self.sid = sid

    async def action_room(self, action, *args, **kwargs):
        result = getattr(self.socketio, f"{action}_room")(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def users_connect(self, auth, namespace):
        print(sc.green(namespace, "reverse"))
        if auth == None:
            return False
        try:
            payload = Token.get_token_payload(auth.get("jwt"))
        except Exception:
            await self.quit_users_rooms(auth.get("jwt"), namespace)
            return False

        if payload.get("desktop_id"):
            with self._rdb_context():
                if (
                    not r.table("domains")
                    .get(payload.get("desktop_id"))
                    .run(self._rdb_connection)
                ):
                    await self.quit_users_rooms(auth.get("jwt"), namespace)
                    return False
            await self.action_room(
                "enter", self.sid, payload.get("desktop_id"), namespace=namespace
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "join_room_desktop_id_direct_viewer",
                        **payload,
                    },
                )
                print(sc.green("join_room_desktop_id_direct_viewer", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
            return True

        if payload.get("user_id"):
            await self.action_room(
                "enter", self.sid, payload["user_id"], namespace=namespace
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "join_room_user_id",
                        **payload,
                    },
                )
                print(sc.green("join_room_user_id", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        if payload.get("role_id") in ["user", "advanced"]:
            return True
        if payload.get("role_id") == "admin":
            await self.action_room("enter", self.sid, "admins", namespace=namespace)
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "join_room_admins",
                        **payload,
                    },
                )
                print(sc.green("join_room_admins", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
            return True
        if payload.get("role_id") == "manager":
            await self.action_room(
                "enter", self.sid, payload.get("category_id"), namespace=namespace
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "join_room_manager",
                        **payload,
                    },
                )
                print(sc.green("join_room_manager", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
            return True

        await self.quit_users_rooms(auth.get("jwt"), namespace)
        if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
            self.logger.error(
                {
                    "websocket": "join_room_users_not_allowed",
                    **payload,
                },
            )
            print(sc.red("join_room_users_not_allowed", "reverse"))
            print(sc.magenta(pformat(payload), "reverse"))
        return False

    async def quit_users_rooms(self, jwt, namespace):
        try:
            payload = Token.get_token_payload(jwt)
        except ExpiredSignatureError:
            payload = Token.get_expired_user_data(jwt)
            if not payload:
                return {}
            self.logger.debug(
                {
                    "websocket": "leave_room_users_expired_token",
                    **payload,
                },
            )
        except Exception:
            payload = Token.get_expired_user_data(jwt)
            if not payload:
                return {}

        if payload.get("desktop_id"):
            await self.action_room(
                "leave", self.sid, payload.get("desktop_id"), namespace=namespace
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "leave_room_desktop_id_direct_viewer",
                        **payload,
                    },
                )
            print(sc.yellow("leave_room_desktop_id_direct_viewer", "reverse"))
            print(sc.magenta(pformat(payload), "reverse"))
        elif payload.get("user_id"):
            await self.action_room(
                "leave", self.sid, payload["user_id"], namespace=namespace
            )
            if os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                self.logger.debug(
                    {
                        "websocket": "leave_room_user_id",
                        **payload,
                    },
                )
                print(sc.yellow("leave_room_user_id", "reverse"))
                print(sc.magenta(pformat(payload), "reverse"))
        return payload
