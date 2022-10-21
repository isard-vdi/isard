#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error
from ..auth.authentication import *
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def get_all_linked_groups(groups):
    with app.app_context():
        linked_groups = list(
            r.table("groups")
            .get_all(r.args(groups), index="id")
            .pluck("linked_groups")
            .run(db.conn)
        )
    for lg in linked_groups:
        groups += lg.get("linked_groups", [])
    return list(dict.fromkeys(groups))


class ApiAllowed:
    def get_table_term(
        self,
        table,
        field,
        value,
        pluck=False,
        query_filter={},
        index_key=None,
        index_value=None,
    ):
        with app.app_context():
            query = r.table(table)
            if index_key and index_value:
                query = query.get_all(index_value, index=index_key)
            if query_filter:
                query = query.filter(query_filter)
            return list(
                query.filter(lambda doc: doc[field].match("(?i)" + value))
                .pluck(pluck)
                .run(db.conn)
            )

    def get_allowed(self, allowed):
        for k, v in allowed.items():
            if v != False and len(v):
                with app.app_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .pluck("id", "name", "uid", "parent_category")
                        .run(db.conn)
                    )
        return allowed

    def get_items_allowed(
        self,
        payload,
        table,
        query_pluck=[],
        query_filter={},
        index_key=None,
        index_value=None,
        order=None,
        query_merge=True,
        extra_ids_allowed=[],
    ):
        try:
            query = r.table(table)
            if index_key and index_value:
                query = query.get_all(index_value, index=index_key)
            if query_filter:
                query = query.filter(query_filter)
            if query_merge:
                query = query.merge(
                    lambda d: {
                        "category_name": r.table("categories")
                        .get(d["category"])["name"]
                        .default(None),
                        "group_name": r.table("groups")
                        .get(d["group"])["name"]
                        .default(None),
                        "user_name": r.table("users")
                        .get(d["user"])["name"]
                        .default(None),
                    }
                )
                if len(query_pluck) > 0:
                    query = query.pluck(
                        query_pluck
                        + [
                            "id",
                            "allowed",
                            "category",
                            "category_name",
                            "group",
                            "group_name",
                            "user",
                            "user_name",
                        ]
                    )
            else:
                if len(query_pluck) > 0:
                    query = query.pluck(["id", "allowed"] + query_pluck)
            if order:
                query = query.order_by(order)
            with app.app_context():
                items = list(query.run(db.conn))

            allowed = []
            for item in items:
                if (
                    payload["role_id"] == "admin"
                    or (
                        payload["role_id"] == "manager"
                        and payload["category_id"] == item.get("category")
                    )
                    or item.get("user") == payload["user_id"]
                ):
                    item["editable"] = True
                else:
                    item["editable"] = False
                if item["id"] in extra_ids_allowed or self.is_allowed(
                    payload, item, table
                ):
                    allowed.append(item)

            return allowed
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )

    def is_allowed(self, payload, item, table):
        if not payload.get("user_id", False):
            return False
        if payload["role_id"] == "admin" or item.get("user") == payload["user_id"]:
            return True
        if item["allowed"]["roles"] is not False:
            if len(item["allowed"]["roles"]) == 0:
                return True
            else:
                if payload["role_id"] in item["allowed"]["roles"]:
                    return True
        if item["allowed"]["categories"] is not False:
            if len(item["allowed"]["categories"]) == 0:
                return True
            else:
                if payload["category_id"] in item["allowed"]["categories"]:
                    return True
        if item["allowed"]["groups"] is not False:
            if len(item["allowed"]["groups"]) == 0:
                if table in ["domains", "media"]:
                    if item.get("category") == payload["category_id"]:
                        return True
                else:
                    return True
            else:
                secondary_groups = (
                    r.table("users")
                    .get(payload["user_id"])
                    .pluck("secondary_groups")
                    .run(db.conn)
                )
                for group in get_all_linked_groups(
                    [payload["group_id"]] + secondary_groups.get("secondary_groups", [])
                ):
                    if group in item["allowed"]["groups"]:
                        return True
        if item["allowed"]["users"] is not False:
            if len(item["allowed"]["users"]) == 0:
                if table in ["domains", "media"]:
                    if item.get("category") == payload["category_id"]:
                        return True
                else:
                    return True
                return False
            else:
                if payload["user_id"] in item["allowed"]["users"]:
                    return True
        return False

    def get_domain_reservables(self, domain_id):
        with app.app_context():
            reservables = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "reservables"})
                .run(db.conn)
            )
        return reservables.get("create_dict", {})
