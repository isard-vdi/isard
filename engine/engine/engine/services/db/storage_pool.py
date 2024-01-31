#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2022 Simó Albert i Beltran
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

from cachetools import TTLCache, cached
from rethinkdb import r

from .db import rethink


@rethink
@cached(
    cache=TTLCache(maxsize=1, ttl=60),
    key=lambda connection: "storage_pools",
)
def get_storage_pools(connection):
    pools = r.table("storage_pool").run(connection)
    return [pool for pool in pools if pool.get("enabled", True)]


def get_storage_pool_ids():
    return [sp["id"] for sp in get_storage_pools()]


def get_storage_pool(storage_pool_id):
    pool = [sp for sp in get_storage_pools() if sp["id"] == storage_pool_id]
    if len(pool) == 0:
        return None
    return pool[0]


def get_category_storage_pool(category_id):
    sps = get_storage_pools()
    default = {}
    for sp in sps:
        # default = uuid4 with zeroes
        if sp["id"] == "00000000-0000-0000-0000-000000000000":
            default = sp
        # TODO: Check if disabled storage?
        if sp.get("category_id", None) == category_id:
            return sp
    return default


def get_category_storage_pool_id(category_id):
    return get_category_storage_pool(category_id)["id"]
