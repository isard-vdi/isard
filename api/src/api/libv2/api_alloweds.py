#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

from ..auth.authentication import *
from .api_exceptions import Error
from .flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)


class ApiAlloweds:
    def get_table_term(self, table, field, value, pluck=False):
        with app.app_context():
            return list(
                r.table(table)
                .filter(lambda doc: doc[field].match("(?i)" + value))
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

    def get_items_allowed(self, payload, table, pluck=[], order=False):
        with app.app_context():
            ud = r.table("users").get(payload["user_id"]).run(db.conn)
            delete_allowed_key = False
            if not "allowed" in pluck:
                pluck.append("allowed")
                delete_allowed_key = True
            allowed_data = {}
            if table == "domains":
                if order:
                    data = (
                        r.table("domains")
                        .get_all("template", index="kind")
                        .order_by(order)
                        .group("category")
                        .pluck({"id", "name", "allowed"})
                        .run(db.conn)
                    )
                else:
                    data = (
                        r.table("domains")
                        .get_all("template", index="kind")
                        .group("category")
                        .pluck({"id", "name", "allowed"})
                        .run(db.conn)
                    )
                for group in data:
                    allowed_data[group] = []
                    for d in data[group]:
                        # False doesn't check, [] means all allowed
                        # Role is the master and user the least. If allowed in roles,
                        #   won't check categories, groups, users
                        allowed = d["allowed"]
                        if d["allowed"]["roles"] != False:
                            if not d["allowed"]["roles"]:  # Len != 0
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                            if ud["role"] in d["allowed"]["roles"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                        if d["allowed"]["categories"] != False:
                            if not d["allowed"]["categories"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                            if ud["category"] in d["allowed"]["categories"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                        if d["allowed"]["groups"] != False:
                            if not d["allowed"]["groups"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                            if ud["group"] in d["allowed"]["groups"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                        if d["allowed"]["users"] != False:
                            if not d["allowed"]["users"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                                continue
                            if user in d["allowed"]["users"]:
                                if delete_allowed_key:
                                    d.pop("allowed", None)
                                allowed_data[group].append(d)
                tmp_data = allowed_data.copy()
                for k, v in tmp_data.items():
                    if not len(tmp_data[k]):
                        allowed_data.pop(k, None)
                return allowed_data
            else:
                if order:
                    data = r.table(table).order_by(order).pluck(pluck).run(db.conn)
                else:
                    data = r.table(table).pluck(pluck).run(db.conn)
            allowed_data = []
            for d in data:
                # False doesn't check, [] means all allowed
                # Role is the master and user the least. If allowed in roles,
                #   won't check categories, groups, users
                allowed = d["allowed"]
                if d["allowed"]["roles"] != False:
                    if not d["allowed"]["roles"]:  # Len != 0
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                    if ud["role"] in d["allowed"]["roles"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                if d["allowed"]["categories"] != False:
                    if not d["allowed"]["categories"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                    if ud["category"] in d["allowed"]["categories"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                if d["allowed"]["groups"] != False:
                    if not d["allowed"]["groups"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                    if ud["group"] in d["allowed"]["groups"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                if d["allowed"]["users"] != False:
                    if not d["allowed"]["users"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
                        continue
                    if ud["id"] in d["allowed"]["users"]:
                        if delete_allowed_key:
                            d.pop("allowed", None)
                        allowed_data.append(d)
            return allowed_data

    def get_domain_reservables(self, domain_id):
        with app.app_context():
            reservables = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "reservables"})
                .run(db.conn)
            )
        return reservables.get("create_dict", {})
