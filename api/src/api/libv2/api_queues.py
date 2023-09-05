#
#   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import os

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from cachetools import TTLCache, cached
from redis import Redis

from .._common.api_rest import ApiRest
from .._common.storage_node import StorageNode


def _connect_redis():
    return Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        password=os.environ.get("REDIS_PASSWORD", ""),
    )


@cached(TTLCache(maxsize=1, ttl=5))
def subscribers():
    with _connect_redis() as r:
        subscribers = r.pubsub_channels()
    s = []
    for subscriber in subscribers:
        s.append(
            {
                "id": str(subscriber).split(":")[3].split("'")[0],
                "type": str(subscriber).split(":")[2],
            }
        )
    return s


@cached(TTLCache(maxsize=1, ttl=5))
def workers():
    with _connect_redis() as r:
        workers = r.keys()
    w = []
    for worker in workers:
        if str(worker).split(":")[1] != "workers":
            continue
        if str(worker).split(":")[2].split(".")[0].split("'")[0] not in [
            "core",
            "storage",
        ]:
            continue
        w.append(
            {
                "id": str(worker).split(":")[2].split("'")[0],
                "type": str(worker).split(":")[2].split(".")[0].split("'")[0],
                "queue_id": str(worker).split(":")[2].split(".")[1]
                if len(str(worker).split(":")[2].split(".")) > 1
                else None,
                "priority_id": str(worker).split(":")[2].split(".")[2].split("'")[0]
                if len(str(worker).split(":")[2].split(".")) > 2
                else None,
            }
        )
    for worker in w:
        if worker["priority_id"] == None:
            worker["priority"] = None
        if worker["priority_id"] == "high":
            worker["priority"] = 3
        if worker["priority_id"] == "default":
            worker["priority"] = 2
        if worker["priority_id"] == "low":
            worker["priority"] = 1
    return w


@cached(TTLCache(maxsize=1, ttl=5))
def workers_with_subscribers():
    w = workers()
    s = subscribers()
    for worker in w:
        worker["subscribers"] = [
            subs["id"] for subs in s if subs["type"] == worker["type"]
        ]
        if not len(worker["subscribers"]):
            worker["status"] = "error"
        else:
            worker["status"] = "ok"
    return w


@cached(TTLCache(maxsize=1, ttl=5))
def subscribers_with_workers():
    s = subscribers()
    w = workers()
    for subscriber in s:
        subscriber["workers"] = [
            worker["id"] for worker in w if subscriber["type"] == worker["type"]
        ]
    return s
