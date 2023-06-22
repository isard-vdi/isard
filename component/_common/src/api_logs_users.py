#
#   Copyright © 2022 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging as log
import os

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from rethinkdb import r


@cached(TTLCache(maxsize=20, ttl=5))
def gen_id(user_id, exp):
    if user_id and exp:
        return user_id + "_" + str(exp)


users_cache = TTLCache(maxsize=200, ttl=60)


def user_key(_, user_id):
    return hashkey(user_id)


class LogsUsers:
    def __init__(self, payload):
        if not payload.get("data", {}).get("group_id"):
            return
        # log.info(f"Last 60 seconds users online: {users_cache.currsize}")
        if payload.get("data", {}).get("user_id") and users_cache.get(
            hashkey(payload.get("data", {}).get("user_id"))
        ):
            # If user is still in cache, do not log
            return
        self.payload = payload
        self.conn = r.connect(
            host=os.environ.get("RETHINKDB_HOST", "isard-db"),
            port=os.environ.get("RETHINKDB_PORT", "28015"),
            db=os.environ.get("RETHINKDB_DB", "isard"),
        )
        if payload.get("data", {}).get("group_id"):
            user = self.get_user(payload["data"]["user_id"])
            if user.get("start_logs_id") == gen_id(
                payload["data"]["user_id"], payload["exp"]
            ):
                self.update(payload)
                self.conn.close()
                return
            self.insert(payload)
            self.conn.close()

    def __exit__(self):
        self.conn.close()

    @cached(users_cache, key=user_key)
    def get_user(self, user_id):
        return (
            r.table("users")
            .get(user_id)
            .pluck("id", "name", "role", "category", "group", "start_logs_id")
            .merge(
                lambda user: {
                    "category_name": r.table("categories").get(user["category"])[
                        "name"
                    ],
                    "group_name": r.table("groups").get(user["group"])["name"],
                }
            )
            .run(self.conn)
        )

    def insert(self, payload):
        user = self.get_user(payload["data"]["user_id"])
        logs = {
            "id": gen_id(payload["data"]["user_id"], payload["exp"]),
            "owner_user_id": payload["data"]["user_id"],
            "owner_user_name": user["name"],
            "owner_role_id": user["role"],
            "owner_category_id": user["category"],
            "owner_category_name": user["category_name"],
            "owner_group_id": user["group"],
            "owner_group_name": user["group_name"],
            "started_time": r.now(),
            "stopped_time": False,
        }
        r.table("logs_users").insert(logs).run(self.conn)
        r.table("users").get(payload["data"]["user_id"]).update(
            {"start_logs_id": gen_id(payload["data"]["user_id"], payload["exp"])},
            durability="soft",
        ).run(self.conn)

    def update(self, payload):
        if (
            not r.table("logs_users")
            .get(gen_id(payload["data"]["user_id"], payload["exp"]))
            .update(
                {"stopped_time": r.now()},
                durability="soft",
            )
            .run(self.conn)
            .get("replaced")
        ):
            self.insert(payload)
