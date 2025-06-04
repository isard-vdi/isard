#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

import gevent
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


@cached(cache=TTLCache(maxsize=20, ttl=5))
def get_user(user_id):
    with app.app_context():
        return (
            r.table("users")
            .get(user_id)
            .without("password", "user_storage")
            .run(db.conn)
        )


@cached(
    cache=TTLCache(maxsize=500, ttl=5),
    key=lambda user_id, user_group_id, groups: hashkey(
        user_id + user_group_id + str(groups)
    ),
)
def check_secondary_groups(user_id, user_group_id, item_allowed_groups):
    secondary_groups = get_user(user_id).get("secondary_groups", [])
    for group in get_all_linked_groups([user_group_id] + secondary_groups):
        if group in item_allowed_groups:
            return True
    return False


@cached(cache=TTLCache(maxsize=10, ttl=5), key=lambda groups: hashkey(str(groups)))
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
        query = r.table(table)
        if index_key and index_value:
            query = query.get_all(index_value, index=index_key)
        if query_filter:
            query = query.filter(query_filter)
        if table == "groups":
            query = query.merge(
                lambda d: {
                    "category_name": r.table("categories")
                    .get(d["parent_category"])
                    .default({"name": "[deleted]"})["name"],
                }
            )
        if table == "users":
            query = query.filter(lambda user: user["active"].eq(True)).merge(
                lambda d: {
                    "category_name": r.table("categories")
                    .get(d["category"])
                    .default({"name": "[deleted]"})["name"],
                    "group_name": r.table("groups")
                    .get(d["group"])
                    .default({"name": "[deleted]"})["name"],
                }
            )
        with app.app_context():
            return list(
                query.filter(lambda doc: doc[field].match("(?i)" + value))
                .pluck(pluck)
                .run(db.conn)
            )

    def get_allowed(self, allowed):
        for k, v in allowed.items():
            if k == "groups" and v != False and len(v):
                with app.app_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .merge(
                            lambda d: {
                                "category_name": r.table("categories")
                                .get(d["parent_category"])
                                .default({"name": "[deleted]"})["name"],
                            }
                        )
                        .pluck("id", "name", "uid", "parent_category", "category_name")
                        .run(db.conn)
                    )
            elif k == "users" and v != False and len(v):
                with app.app_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .merge(
                            lambda d: {
                                "category_name": r.table("categories")
                                .get(d["category"])
                                .default({"name": "[deleted]"})["name"],
                                "group_name": r.table("groups")
                                .get(d["group"])
                                .default({"name": "[deleted]"})["name"],
                            }
                        )
                        .pluck("id", "name", "uid", "group_name", "category_name")
                        .run(db.conn)
                    )
            elif v != False and len(v):
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
        only_in_allowed=False,
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
                    payload, item, table, ignore_role=only_in_allowed
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

    def is_allowed(self, payload, item, table, ignore_role=False):
        if not payload.get("user_id", False):
            return False
        if not ignore_role and (
            payload["role_id"] == "admin"
            or item.get("user") == payload["user_id"]
            or (
                payload["role_id"] == "manager"
                and item.get("category") == payload["category_id"]
            )
        ):
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
                if check_secondary_groups(
                    payload["user_id"], payload["group_id"], item["allowed"]["groups"]
                ):
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

    def get_users_allowed(self, allowed):
        users = []
        for k, v in allowed.items():
            if k == "categories" and v != False and len(v):
                with app.app_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="category")
                        .pluck("id")["id"]
                        .run(db.conn)
                    )
            elif k == "groups" and v != False and len(v):
                with app.app_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="group")
                        .pluck("id")["id"]
                        .run(db.conn)
                    )
            elif k == "users" and v != False and len(v):
                with app.app_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="id")
                        .pluck("id")["id"]
                        .run(db.conn)
                    )
            elif k == "roles" and v != False and len(v):
                with app.app_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="role")
                        .pluck("id")["id"]
                        .run(db.conn)
                    )
            elif v == []:
                with app.app_context():
                    users.append(r.table("users").pluck("id")["id"].run(db.conn))

        # remove duplicates
        users = [item for sublist in users for item in sublist]

        return users

    def remove_disallowed_bastion_targets(self):
        with app.app_context():
            targets = r.table("targets").run(db.conn)

        with app.app_context():
            bastion_alloweds = dict(
                r.table("config")
                .get(1)
                .pluck([{"bastion": "allowed"}])
                .run(db.conn)["bastion"]["allowed"]
            )

        allowed_users = self.get_users_allowed(bastion_alloweds)

        disallowed_targets = []

        for target in targets:
            if target["user_id"] not in allowed_users:
                disallowed_targets.append(target["id"])

        with app.app_context():
            r.table("targets").get_all(r.args(disallowed_targets)).delete().run(db.conn)

        return disallowed_targets

    def remove_disallowed_bastion_targets_th(self):
        gevent.spawn(self.remove_disallowed_bastion_targets)

    def update_bastion_alloweds(self, allowed):
        with app.app_context():
            r.table("config").get(1).update(
                {
                    "bastion": {
                        "allowed": allowed,
                    }
                }
            ).run(db.conn)

    def remove_disallowed_bastion_target_domains(self):
        with app.app_context():
            targets = r.table("targets").run(db.conn)

        with app.app_context():
            bastion_alloweds = dict(
                r.table("config")
                .get(1)
                .pluck([{"bastion": {"individual_domains": "allowed"}}])
                .run(db.conn)["bastion"]["individual_domains"]["allowed"]
            )

        allowed_users = self.get_users_allowed(bastion_alloweds)

        disallowed_targets = []

        for target in targets:
            if target["user_id"] not in allowed_users:
                disallowed_targets.append(target["id"])

        with app.app_context():
            r.table("targets").get_all(r.args(disallowed_targets)).update(
                {
                    "domain": None,
                }
            ).run(db.conn)

        return disallowed_targets

    def remove_disallowed_bastion_target_domains_th(self):
        gevent.spawn(self.remove_disallowed_bastion_target_domains)

    def update_bastion_target_domains_alloweds(self, allowed):
        with app.app_context():
            r.table("config").get(1).update(
                {
                    "bastion": {
                        "individual_domains": {
                            "allowed": allowed,
                        }
                    }
                }
            ).run(db.conn)
