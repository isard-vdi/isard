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
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from rethinkdb import r

from .db import rethink


@rethink
@cached(
    cache=TTLCache(maxsize=1, ttl=10),
    key=lambda connection: "storage_pools",
)
def get_all_storage_pools(connection):
    storage_pools = []
    for sp in r.table("storage_pool").run(connection):
        if sp["id"] == DEFAULT_STORAGE_POOL_ID:
            sp = _parse_default_storage_pool_paths(sp)
        storage_pools.append(sp)
    return storage_pools


@rethink
@cached(
    cache=TTLCache(maxsize=1, ttl=10),
    key=lambda connection: "storage_pools",
)
def get_storage_pools(connection):
    storage_pools = []
    for sp in r.table("storage_pool").filter({"enabled": True}).run(connection):
        if sp["id"] == DEFAULT_STORAGE_POOL_ID:
            sp = _parse_default_storage_pool_paths(sp)
        storage_pools.append(sp)
    return storage_pools


def get_storage_pool_ids(only_enabled=True):
    if only_enabled:
        return [sp["id"] for sp in get_storage_pools()]
    return [sp["id"] for sp in get_all_storage_pools()]


def get_category_storage_pool(category_id):
    sps = get_storage_pools()
    default = None
    for sp in sps:
        # If no category is found, return default storage pool
        if sp["id"] == DEFAULT_STORAGE_POOL_ID:
            default = sp
        if category_id in sp.get("categories", []):
            return _parse_category_storage_pool_paths(sp, category_id)
    return default


def get_default_storage_pool():
    return [sp for sp in get_storage_pools() if sp["id"] == DEFAULT_STORAGE_POOL_ID][0]


def get_category_storage_pool_id(category_id):
    storage_pool = get_category_storage_pool(category_id)
    if storage_pool is None:
        return None
    return storage_pool["id"]


def _parse_category_storage_pool_paths(pool, category_id):
    parsed_pool = pool.copy()
    if pool["id"] == DEFAULT_STORAGE_POOL_ID:
        return parsed_pool
    type_paths = ["desktop", "media", "template", "volatile"]
    pool_paths = {}
    for type_path in type_paths:
        paths = parsed_pool["paths"].get(type_path, [])
        if not len(paths):
            path_list = get_default_storage_pool()["paths"].get(type_path, [])
            pool_paths[type_path] = path_list
            continue
        path_list = []
        for path in paths:
            path_key = (
                parsed_pool["mountpoint"] + "/" + category_id + "/" + path["path"]
            )
            path_list.append({"path": path_key, "weight": path["weight"]})
        pool_paths[type_path] = path_list
    parsed_pool["paths"] = pool_paths.copy()
    return parsed_pool


def _parse_default_storage_pool_paths(pool):
    if pool["id"] != DEFAULT_STORAGE_POOL_ID:
        return False
    type_paths = ["desktop", "media", "template", "volatile"]
    pool_paths = {}
    for type_path in type_paths:
        paths = pool["paths"].get(type_path, [])
        path_list = []
        for path in paths:
            path_key = "/isard/" + path["path"]
            path_list.append({"path": path_key, "weight": path["weight"]})
        pool_paths[type_path] = path_list
    pool["paths"] = pool_paths
    return pool
