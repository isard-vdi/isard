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
from rethinkdb import RethinkDB
from rethinkdb.errors import ReqlNonExistenceError

from api import app

from ..flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


@cached(cache=TTLCache(maxsize=1000, ttl=240))
def get_group_name(group_id):
    try:
        with app.app_context():
            group = r.table("groups").get(group_id).pluck("name").run(db.conn)
    except ReqlNonExistenceError:
        group = {"name": "[DELETED]"}
    return group["name"]


@cached(cache=TTLCache(maxsize=1000, ttl=240))
def get_category_name(category_id):
    try:
        with app.app_context():
            category = r.table("categories").get(category_id).pluck("name").run(db.conn)
    except ReqlNonExistenceError:
        category = {"name": "[DELETED]"}
    return category["name"]


def get_owner_info(user_id):
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


@cached(cache=TTLCache(maxsize=1, ttl=240))
def get_owners_info():
    with app.app_context():
        users = list(
            r.table("users").pluck("id", "name", "group", "category").run(db.conn)
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


def get_abs_consumptions(item_type, date):
    # TODO: Check that it gets the correct one from date
    with app.app_context():
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
            .run(db.conn, array_limit=200000)
        )


@cached(cache=TTLCache(maxsize=100, ttl=60))
def get_params():
    with app.app_context():
        return (
            r.table("usage_parameter")
            .group("item_type")
            .ungroup()
            .map(lambda item: [item["group"], item["reduction"]])
            .coerce_to("object")
            .run(db.conn)
        )


def get_default_consumption(parameters_ids=None):
    query = r.table("usage_parameter")
    if parameters_ids:
        query = query.get_all(r.args(parameters_ids))
    with app.app_context():
        default_consumption = list(query.run(db.conn))
    return {dc["id"]: dc["default"] for dc in default_consumption}


@cached(cache=TTLCache(maxsize=100, ttl=60))
def get_params_item_type_custom(item_type, custom):
    with app.app_context():
        return list(
            r.table("usage_parameter")
            .get_all([custom, item_type], index="custom_type")
            .run(db.conn)
        )


# TODO: This should be checked when adding a new formula, not at each call
def securize_eval(formula, safe_dict):
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
    )
    tree = ast.parse(formula, mode="eval")
    valid = all(isinstance(node, whitelist) for node in ast.walk(tree))
    if valid:
        return eval(
            compile(tree, filename="", mode="eval"), {"__builtins__": None}, safe_dict
        )
