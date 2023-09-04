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
def active_clients():
    with _connect_redis() as redis:
        clients = [
            client for client in redis.client_list() if client.get("name", "") != ""
        ]
    data = []
    for client in clients:
        data.append(
            {
                "id": client.get("name").split(":")[1],
                "type": client.get("name").split(":")[0],
            }
        )
    return data
