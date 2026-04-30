# Usage consolidation helpers
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r

log = logging.getLogger("apiv4")

#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import ast
from datetime import datetime, timedelta

from cachetools import TTLCache, cached
from rethinkdb.errors import ReqlNonExistenceError

# Named caches so writers can invalidate them after mutations.
group_name_cache: TTLCache = TTLCache(maxsize=1000, ttl=240)
category_name_cache: TTLCache = TTLCache(maxsize=1000, ttl=240)
owners_info_cache: TTLCache = TTLCache(maxsize=1, ttl=240)
params_cache: TTLCache = TTLCache(maxsize=100, ttl=60)
params_item_type_custom_cache: TTLCache = TTLCache(maxsize=100, ttl=60)


def clear_usage_caches() -> None:
    """Clear all usage helper caches at once.

    Usage parameters are admin-edited via the usage admin endpoints;
    a single sweep helper keeps writers from having to know each
    cache name.
    """
    group_name_cache.clear()
    category_name_cache.clear()
    owners_info_cache.clear()
    params_cache.clear()
    params_item_type_custom_cache.clear()


@cached(cache=group_name_cache)
def get_group_name(group_id: str) -> str:
    try:
        with RethinkSharedConnection._rdb_context():
            group = (
                r.table("groups")
                .get(group_id)
                .pluck("name")
                .run(RethinkSharedConnection._rdb_connection)
            )
    except ReqlNonExistenceError:
        group = {"name": "[DELETED]"}
    return group["name"]


@cached(cache=category_name_cache)
def get_category_name(category_id: str) -> str:
    try:
        with RethinkSharedConnection._rdb_context():
            category = (
                r.table("categories")
                .get(category_id)
                .pluck("name")
                .run(RethinkSharedConnection._rdb_connection)
            )
    except ReqlNonExistenceError:
        category = {"name": "[DELETED]"}
    return category["name"]


def get_owner_info(user_id: str) -> dict:
    if user_id in get_owners_info():
        return get_owners_info()[user_id]
    else:
        return {
            "owner_user_id": user_id,
            "owner_user_name": "[DELETED]",
            "owner_group_id": "[USER DELETED]",
            "owner_group_name": "[USER DELETED]",
            "owner_category_id": "[USER DELETED]",
            "owner_category_name": "[USER DELETED]",
        }


@cached(cache=owners_info_cache)
def get_owners_info() -> dict:
    with RethinkSharedConnection._rdb_context():
        users = list(
            r.table("users")
            .pluck("id", "name", "group", "category")
            .run(RethinkSharedConnection._rdb_connection)
        )
    return {
        user["id"]: {
            "owner_user_id": user["id"],
            "owner_user_name": user["name"],
            "owner_group_id": user["group"],
            "owner_group_name": get_group_name(user["group"]),
            "owner_category_id": user["category"],
            "owner_category_name": get_category_name(user["category"]),
        }
        for user in users
    }


def get_abs_consumptions(item_type: str, date: datetime) -> dict:
    # TODO: Check that it gets the correct one from date
    with RethinkSharedConnection._rdb_context():
        return (
            r.table("usage_consumption")
            .get_all(item_type, index="item_type")
            .filter(r.row["date"] <= date)
            .group("item_id", "item_consumer")
            .max("date")
            .ungroup()
            .map(
                lambda item: [
                    item["group"][0] + "##" + item["group"][1],
                    item["reduction"],
                ]
            )
            .coerce_to("object")
            .run(RethinkSharedConnection._rdb_connection, array_limit=300000)
        )


@cached(cache=params_cache)
def get_params() -> dict:
    with RethinkSharedConnection._rdb_context():
        return (
            r.table("usage_parameter")
            .group("item_type")
            .ungroup()
            .map(lambda item: [item["group"], item["reduction"]])
            .coerce_to("object")
            .run(RethinkSharedConnection._rdb_connection)
        )


def get_default_consumption(parameters_ids: list[str] | None = None) -> dict:
    query = r.table("usage_parameter")
    if parameters_ids:
        query = query.get_all(r.args(parameters_ids))
    with RethinkSharedConnection._rdb_context():
        default_consumption = list(query.run(RethinkSharedConnection._rdb_connection))
    return {dc["id"]: dc["default"] for dc in default_consumption}


@cached(cache=params_item_type_custom_cache)
def get_params_item_type_custom(item_type: str, custom: bool) -> list[dict]:
    with RethinkSharedConnection._rdb_context():
        return list(
            r.table("usage_parameter")
            .get_all([custom, item_type], index="custom_type")
            .run(RethinkSharedConnection._rdb_connection)
        )


# TODO: This should be checked when adding a new formula, not at each call
def securize_eval(formula: str, safe_dict: dict):
    whitelist = (
        ast.Expression,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.BinOp,
        ast.UnaryOp,
        ast.operator,
        ast.unaryop,
        ast.cmpop,
        ast.Num,
        ast.Constant,
    )
    denylist = (ast.Attribute, ast.Subscript, ast.Import, ast.ImportFrom)
    tree = ast.parse(formula, mode="eval")
    has_denied = any(isinstance(node, denylist) for node in ast.walk(tree))
    if has_denied:
        raise ValueError(f"Formula contains forbidden constructs: {formula}")
    valid = all(isinstance(node, whitelist) for node in ast.walk(tree))
    if valid:
        # Safe eval: AST-validated formula with builtins disabled
        return eval(
            compile(tree, filename="", mode="eval"), {"__builtins__": None}, safe_dict
        )
    raise ValueError(f"Formula contains non-whitelisted constructs: {formula}")
