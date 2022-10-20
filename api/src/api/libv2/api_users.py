#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import time
from datetime import datetime, timedelta

from rethinkdb import RethinkDB

from api import app

from .api_desktop_events import desktops_delete
from .api_exceptions import Error
from .quotas import Quotas

quotas = Quotas()

r = RethinkDB()
import logging as log
import traceback
from string import ascii_lowercase, digits

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .api_admin import (
    change_category_items_owner,
    change_group_items_owner,
    change_user_items_owner,
)
from .ds import DS
from .helpers import _check, _parse_desktop, _random_password, gen_payload_from_user

ds = DS()

import os
import secrets

import bcrypt
from jose import jwt


def check_category_domain(category_id, domain):
    with app.app_context():
        allowed_domain = (
            r.table("categories")
            .get(category_id)
            .pluck("allowed_domain")
            .run(db.conn)
            .get("allowed_domain")
        )
    allowed = not allowed_domain or domain == allowed_domain
    if not allowed:
        raise Error(
            "forbidden",
            "Register domain does not match category allowed domain",
            traceback.format_exc(),
        )


class ApiUsers:
    def Jwt(self, user_id, minutes=240):
        return {
            "jwt": jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(minutes=minutes),
                    "kid": "isardvdi",
                    "data": gen_payload_from_user(user_id),
                },
                app.ram["secrets"]["isardvdi"]["secret"],
                algorithm="HS256",
            )
        }

    def Login(self, user_id, user_passwd, provider="local", category_id="default"):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if user is None:
            raise Error("unauthorized", "", traceback.format_exc())
        if not user.get("active", False):
            raise Error(
                "unauthorized",
                "User " + user_id + " is disabled",
                traceback.format_exc(),
            )

        pw = Password()
        if pw.valid(user_passwd, user["password"]):
            user = {
                "user_id": user["id"],
                "role_id": user["role"],
                "category_id": user["category"],
                "group_id": user["group"],
                "username": user["username"],
                "email": user["email"],
                "photo": user["photo"],
            }
            return user_id, jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(hours=4),
                    "kid": "isardvdi",
                    "data": user,
                },
                app.ram["secrets"]["isardvdi"]["secret"],
                algorithm="HS256",
            )
        raise Error(
            "unauthorized",
            "Invalid login credentials for user_id " + user_id,
            traceback.format_exc(),
        )

    def Config(self, payload):
        show_bookings_button = (
            True
            if payload["role_id"] == "admin"
            or os.environ.get("FRONTEND_SHOW_BOOKINGS") == "True"
            else False
        )
        frontend_show_temporal_tab = (
            True
            if os.environ.get("FRONTEND_SHOW_TEMPORAL") == None
            else os.environ.get("FRONTEND_SHOW_TEMPORAL") == "True"
        )

        return {
            **{
                "show_bookings_button": show_bookings_button,
                "documentation_url": os.environ.get(
                    "FRONTEND_DOCS_URI", "https://isard.gitlab.io/isardvdi-docs/"
                ),
                "show_temporal_tab": frontend_show_temporal_tab,
            },
        }

    def Get(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                        "role_name": r.table("roles").get(d["role"])["name"],
                    }
                )
                .without("password")
                .run(db.conn)
            )
        if not user:
            raise Error(
                "not_found",
                "Not found user_id " + user_id,
                traceback.format_exc(),
            )
        return {**user, **quotas.Get(user_id)}

    def GetByProviderCategoryUID(self, provider, category, uid):
        with app.app_context():
            user = list(
                r.table("users")
                .get_all([uid, category, provider], index="uid_category_provider")
                .run(db.conn)
            )
        return user

    def List(self, category_id=None):
        query = r.table("users")
        if category_id:
            query = query.get_all(category_id, index="category")
        query = query.without("password", {"vpn": {"wireguard": "keys"}}).merge(
            lambda user: {
                "desktops": r.table("domains")
                .get_all(["desktop", user["id"]], index="kind_user")
                .count(),
                "templates": r.table("domains")
                .get_all(["template", user["id"]], index="kind_user")
                .count(),
                "secondary_groups_data": r.table("groups")
                .get_all(r.args(user["secondary_groups"]))
                .pluck("id", "name")
                .coerce_to("array"),
            }
        )
        with app.app_context():
            return list(query.run(db.conn))

    # this method is needed for user auto-registering
    # It will get the quota from the user group provided
    def Create(
        self,
        provider,
        category_id,
        user_uid,
        user_username,
        name,
        role_id,
        group_id,
        password=False,
        encrypted_password=False,
        photo="",
        email="",
    ):
        # password=False generates a random password
        with app.app_context():
            user_id = (
                provider + "-" + category_id + "-" + user_uid + "-" + user_username
            )
            if r.table("users").get(user_id).run(db.conn) != None:
                raise Error(
                    "conflict",
                    "Already exists user_id " + user_id,
                    traceback.format_exc(),
                )

            if r.table("roles").get(role_id).run(db.conn) is None:
                raise Error(
                    "not_found",
                    "Not found role_id " + role_id + " for user_id " + user_id,
                    traceback.format_exc(),
                )

            if r.table("categories").get(category_id).run(db.conn) is None:
                raise Error(
                    "not_found",
                    "Not found category_id " + category_id + " for user_id " + user_id,
                    traceback.format_exc(),
                )

            group = r.table("groups").get(group_id).run(db.conn)
            if group is None:
                raise Error(
                    "not_found",
                    "Not found group_id " + group_id + " for user_id " + user_id,
                    traceback.format_exc(),
                )

            if password == False:
                password = _random_password()
            else:
                bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
                    "utf-8"
                )
            if encrypted_password != False:
                password = encrypted_password

            user = {
                "id": user_id,
                "name": name,
                "uid": user_uid,
                "provider": provider,
                "active": True,
                "accessed": int(time.time()),
                "username": user_username,
                "password": password,
                "role": role_id,
                "category": category_id,
                "group": group_id,
                "email": email,
                "photo": photo,
                "default_templates": [],
                "quota": group["quota"],  # 10GB
                "secondary_groups": [],
            }
            if not _check(r.table("users").insert(user).run(db.conn), "inserted"):
                raise Error(
                    "internal_server",
                    "Unable to insert in database user_id " + user_id,
                    traceback.format_exc(),
                )
        return user_id

    def Update(
        self,
        user_id,
        name=None,
        email=None,
        photo=None,
        password=None,
        role=None,
        quota=None,
    ):
        self.Get(user_id)
        update_values = {}
        if name:
            update_values["name"] = name
        if email:
            update_values["email"] = email
        if photo:
            update_values["photo"] = photo
        if role:
            update_values["role"] = role
        if quota is not None:
            update_values["quota"] = quota

        if password:
            p = Password()
            update_values["password"] = p.encrypt(password)
        if update_values:
            with app.app_context():
                if not _check(
                    r.table("users").get(user_id).update(update_values).run(db.conn),
                    "replaced",
                ):
                    raise Error(
                        "internal_server",
                        "Unable to update in database user_id " + user_id,
                        traceback.format_exc(),
                    )

    def Templates(self, payload):
        try:
            with app.app_context():
                return list(
                    r.table("domains")
                    .get_all(["template", payload["user_id"]], index="kind_user")
                    .order_by("name")
                    .pluck(
                        {
                            "id",
                            "name",
                            "allowed",
                            "enabled",
                            "kind",
                            "category",
                            "group",
                            "icon",
                            "image",
                            "user",
                            "description",
                        }
                    )
                    .run(db.conn)
                )
        except Exception:
            raise Error(
                "internal_server", "Internal server error", traceback.format_exc()
            )

    def Desktops(self, user_id):
        self.Get(user_id)
        try:
            with app.app_context():
                desktops = list(
                    r.table("domains")
                    .get_all(["desktop", user_id], index="kind_user")
                    .order_by("name")
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "guest_properties",
                            "tag",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {
                                "create_dict": {
                                    "hardware": ["interfaces", "videos"],
                                    "reservables": True,
                                }
                            },
                            "server",
                            "progress",
                            "booking_id",
                            "scheduled",
                        ]
                    )
                    .run(db.conn)
                )
            return [
                _parse_desktop(desktop)
                for desktop in desktops
                if not desktop.get("tag")
                or desktop.get("tag")
                and desktop.get("tag_visible")
            ]
        except:
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )

    def Desktop(self, desktop_id, user_id):
        self.Get(user_id)
        try:
            with app.app_context():
                desktop = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "guest_properties",
                            "tag",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {
                                "create_dict": {
                                    "hardware": ["interfaces", "videos"],
                                    "reservables": True,
                                }
                            },
                            "progress",
                            "booking_id",
                        ]
                    )
                    .run(db.conn)
                )
            if (
                not desktop.get("tag")
                or desktop.get("tag")
                and desktop.get("tag_visible")
            ):
                return _parse_desktop(desktop)
            else:
                raise Error(
                    "forbidden",
                    "Desktop is not visible to this user now.",
                    description_code="desktop_is_not_visible",
                )
        except:
            raise Error(
                "not_found",
                "Desktop not found",
                traceback.format_exc(),
                description_code="desktop_not_found",
            )

    def Delete(self, user_id):
        self.Get(user_id)
        desktops_delete(
            [desktop["id"] for desktop in self._delete_checks(user_id, "user")],
            from_started=True,
            wait_seconds=30,
        )

        change_user_items_owner("media", user_id)
        with app.app_context():
            if not _check(
                r.table("users").get(user_id).delete().run(db.conn), "deleted"
            ):
                raise Error(
                    "internal_server",
                    "Unable to delete user_id " + user_id,
                    traceback.format_exc(),
                    description_code="unable_to_delete_user" + user_id,
                )

    def _delete_checks(self, item_id, table):
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(item_id, index=table)
                .filter({"kind": "desktop"})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .filter({table: item_id})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )

            users = []
            if table == "category" or table == "group":
                users = list(
                    r.table("users")
                    .get_all(item_id, index=table)
                    .pluck("id", "name")
                    .run(db.conn)
                )
            for u in users:
                u.update({"kind": "user", "user": u["id"]})

            groups = []
            if table == "category":
                groups = list(
                    r.table("groups")
                    .get_all(item_id, index="parent_category")
                    .pluck("id", "name")
                    .run(db.conn)
                )

            for g in groups:
                g.update({"kind": "group", "user": g["id"]})

            derivated = []
            for ut in templates:
                template_id = ut["id"]
                derivated = derivated + list(
                    r.table("domains")
                    .pluck("id", "name", "kind", "user", "status", "parents")
                    .filter(
                        lambda derivates: derivates["parents"].contains(template_id)
                    )
                    .run(db.conn)
                )

        domains = desktops + templates + derivated + users + groups
        return [i for n, i in enumerate(domains) if i not in domains[n + 1 :]]

    def OwnsDesktop(self, user_id, guess_ip):
        with app.app_context():
            ips = list(
                r.table("domains")
                .get_all(user_id, index="user")
                .pluck({"viewer": "guest_ip"})
                .run(db.conn)
            )
        if len(
            [
                ip
                for ip in ips
                if ip.get("viewer", False)
                and ip["viewer"].get("guest_ip", False) == guess_ip
            ]
        ):
            return True
        raise Error(
            "forbidden",
            "Forbidden access to desktop viewer",
            traceback.format_exc(),
        )

    def CodeSearch(self, code):
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"manager": code}}).run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {
                    "role": "manager",
                    "category": category,
                    "group": found[0]["id"],
                }
            found = list(
                r.table("groups")
                .filter({"enrollment": {"advanced": code}})
                .run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {
                    "role": "advanced",
                    "category": category,
                    "group": found[0]["id"],
                }
            found = list(
                r.table("groups").filter({"enrollment": {"user": code}}).run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {"role": "user", "category": category, "group": found[0]["id"]}
        raise Error(
            "not_found",
            "Code not found code:" + code,
            traceback.format_exc(),
            description_code="code_not_found: " + code,
        )

    def CategoryGet(self, category_id, all=False):
        with app.app_context():
            category = r.table("categories").get(category_id).run(db.conn)
        if not category:
            raise Error(
                "not_found",
                "Category not found category_id:" + category_id,
                traceback.format_exc(),
                description_code="category_not_found",
            )
        if not all:
            return {"name": category["name"]}
        else:
            return category

    def CategoryGetByName(self, category_name):
        with app.app_context():
            category = list(
                r.table("categories")
                .filter(lambda category: category["name"].match("(?i)" + category_name))
                .run(db.conn)
            )
        if not category:
            raise Error(
                "not_found",
                "Category name " + category_name + " not found",
                traceback.format_exc(),
            )
        else:
            return category[0]

    ### USER Schema

    def CategoriesGet(self):
        with app.app_context():
            return list(
                r.table("categories")
                .pluck({"id", "name", "frontend"})
                .order_by("name")
                .run(db.conn)
            )

    def CategoriesFrontendGet(self):
        with app.app_context():
            return list(
                r.table("categories")
                .pluck({"id", "name", "frontend"})
                .filter({"frontend": True})
                .order_by("name")
                .run(db.conn)
            )

    def category_delete_checks(self, category_id):
        with app.app_context():
            category = (
                r.table("categories").get(category_id).pluck("id", "name").run(db.conn)
            )
            if not category:
                raise Error(
                    "not_found",
                    "Category to delete not found.",
                    traceback.format_exc(),
                    description_code="category_not_found",
                )
            else:
                category.update({"kind": "category", "user": category["id"]})
                categories = [category]
            groups = list(
                r.table("groups")
                .filter({"parent_category": category_id})
                .pluck("id", "name")
                .run(db.conn)
            )
            for g in groups:
                g.update({"kind": "group", "user": g["id"]})
            users = list(
                r.table("users")
                .get_all(category_id, index="category")
                .pluck("id", "name")
                .run(db.conn)
            )
            for u in users:
                u.update({"kind": "user", "user": u["id"]})

            category_desktops = list(
                r.table("domains")
                .get_all(["desktop", category_id], index="kind_category")
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            category_templates = list(
                r.table("domains")
                .get_all(["template", category_id], index="kind_category")
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            derivated = []
            for ut in category_templates:
                id = ut["id"]
                derivated = derivated + list(
                    r.table("domains")
                    .pluck("id", "name", "kind", "user", "status", "parents")
                    .filter(lambda derivates: derivates["parents"].contains(id))
                    .run(db.conn)
                )
        domains = (
            categories
            + groups
            + users
            + category_desktops
            + category_templates
            + derivated
        )
        return [i for n, i in enumerate(domains) if i not in domains[n + 1 :]]

    def CategoryDelete(self, category_id):
        desktops_to_delete = []
        with app.app_context():
            for d in self.category_delete_checks(category_id):
                if d["kind"] == "user":
                    r.table("users").get(d["id"]).delete().run(db.conn)
                elif d["kind"] == "group":
                    r.table("groups").get(d["id"]).delete().run(db.conn)
                elif d["kind"] == "category":
                    r.table("categories").get(d["id"]).delete().run(db.conn)
                else:
                    desktops_to_delete.append(d["id"])
        desktops_delete(
            desktops_to_delete,
            from_started=True,
            wait_seconds=30,
        )
        change_category_items_owner("media", category_id)

    def GroupGet(self, group_id):
        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
        if not group:
            raise Error(
                "not_found",
                "Not found group_id " + group_id,
                traceback.format_exc(),
                description_code="group_not_found",
            )
        return group

    def GroupGetByNameCategory(self, group_name, category_id):
        with app.app_context():
            group = list(
                r.table("groups")
                .get_all(category_id, index="parent_category")
                .filter({"name": group_name})
                .run(db.conn)
            )
        if not group:
            raise Error(
                "not_found",
                "Not found group name " + group_name,
                traceback.format_exc(),
            )
        return group[0]

    def GroupsGet(self):
        return list(
            r.table("groups")
            .order_by("name")
            .merge(
                lambda group: {
                    "linked_groups_data": r.table("groups")
                    .get_all(r.args(group["linked_groups"]))
                    .pluck("id", "name")
                    .coerce_to("array"),
                }
            )
            .run(db.conn)
        )

    def group_delete_checks(self, group_id):
        with app.app_context():
            group = r.table("groups").get(group_id).pluck("id", "name").run(db.conn)
            if not group:
                raise Error(
                    "not_found",
                    "Group to delete not found",
                    traceback.format_exc(),
                    description_code="group_not_found",
                )
            else:
                group.update({"kind": "group", "user": group["id"]})
                groups = [group]
            users = list(
                r.table("users")
                .get_all(group_id, index="group")
                .pluck("id", "name")
                .run(db.conn)
            )
            for u in users:
                u.update({"kind": "user", "user": u["id"]})

            desktops = list(
                r.table("domains")
                .get_all(["desktop", group_id], index="kind_group")
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            group_templates = list(
                r.table("domains")
                .get_all(["template", group_id], index="kind_group")
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            derivated = []
            for gt in group_templates:
                id = gt["id"]
                derivated = derivated + list(
                    r.table("domains")
                    .pluck("id", "name", "kind", "user", "status", "parents")
                    .filter(lambda derivates: derivates["parents"].contains(id))
                    .run(db.conn)
                )
        domains = groups + users + desktops + group_templates + derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1 :]]

    def GroupDelete(self, group_id):

        self.GroupGet(group_id)

        with app.app_context():
            category = (
                r.table("groups")
                .get(group_id)
                .default({"parent_category": None})
                .run(db.conn)["parent_category"]
            )
        if not category:
            raise Error(
                "not_found",
                "Group id " + str(group_id) + " not found",
                description_code="group_not_found",
            )

        desktops = (
            r.table("domains")
            .get_all(group_id, index="group")
            .pluck("id", "status")
            .run(db.conn)
        )

        desktops_delete(
            [desktop["id"] for desktop in desktops],
            from_started=True,
            wait_seconds=30,
        )

        desktops_to_delete = []
        with app.app_context():
            for d in self.group_delete_checks(group_id):
                if d["kind"] == "user":
                    r.table("users").get(d["id"]).delete().run(db.conn)
                elif d["kind"] == "group":
                    r.table("groups").get(d["id"]).delete().run(db.conn)
                else:
                    desktops_to_delete.append(d["id"])
        desktops_delete(
            desktops_to_delete,
            from_started=True,
            wait_seconds=30,
        )
        change_group_items_owner("media", group_id)

    def EnrollmentAction(self, data):
        if data["action"] == "disable":
            with app.app_context():
                r.table("groups").get(data["id"]).update(
                    {"enrollment": {data["role"]: False}}
                ).run(db.conn)
            return True
        if data["action"] == "reset":
            chars = digits + ascii_lowercase
        code = False
        while code == False:
            code = "".join([random.choice(chars) for i in range(6)])
            if self.enrollment_code_check(code) == False:
                with app.app_context():
                    r.table("groups").get(data["id"]).update(
                        {"enrollment": {data["role"]: code}}
                    ).run(db.conn)
                return code
        raise Error(
            "internal_server",
            "Unable to generate enrollment code",
            traceback.format_exc(),
            description_code="unable_to_gen_enrollment_code",
        )

    def enrollment_code_check(self, code):
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"manager": code}}).run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {
                    "code": code,
                    "role": "manager",
                    "category": category,
                    "group": found[0]["id"],
                }
            found = list(
                r.table("groups")
                .filter({"enrollment": {"advanced": code}})
                .run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {
                    "code": code,
                    "role": "advanced",
                    "category": category,
                    "group": found[0]["id"],
                }
            found = list(
                r.table("groups").filter({"enrollment": {"user": code}}).run(db.conn)
            )
            if len(found) > 0:
                category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
                return {
                    "code": code,
                    "role": "user",
                    "category": category,
                    "group": found[0]["id"],
                }
        return False

    def UpdateGroupQuota(self, group, quota, propagate):
        category = self.CategoryGet(group["parent_category"], True)

        # Limit group limits to it's category limits
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if quota and quota.get("users") and v < quota[k]:
                    quota[k] = v

        with app.app_context():
            r.table("groups").get(group["id"]).update({"quota": quota}).run(db.conn)

        if propagate:
            r.table("users").get_all(group["id"], index="group").update(
                {"quota": quota}
            ).run(db.conn)

    def UpdateCategoryQuota(self, category_id, quota, propagate):
        with app.app_context():
            r.table("categories").get(category_id).update({"quota": quota}).run(db.conn)
        if propagate:
            with app.app_context():
                for group in list(
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .run(db.conn)
                ):
                    self.UpdateGroupQuota(group, quota, propagate)

    def UpdateGroupLimits(self, group, limits):
        category = self.CategoryGet(group["parent_category"], True)

        # Limit group limits to it's category limits
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if v < limits[k]:
                    limits[k] = v

        with app.app_context():
            r.table("groups").get(group["id"]).update({"limits": limits}).run(db.conn)

    def UpdateCategoryLimits(self, category_id, limits, propagate):
        with app.app_context():
            r.table("categories").get(category_id).update({"limits": limits}).run(
                db.conn
            )
        if propagate:
            with app.app_context():
                r.table("groups").get_all(category_id, index="parent_category").update(
                    {"limits": limits}
                ).run(db.conn)

    def WebappDesktops(self, user_id):
        self.Get(user_id)
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .order_by("name")
                .without("xml", "history_domain", "allowed")
                .run(db.conn)
            )
        return [
            d
            for d in desktops
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]

    def WebappTemplates(self, user_id):
        with app.app_context():
            templates = list(
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")
                .without("viewer", "xml", "history_domain")
                .run(db.conn)
            )
        return templates

    def groups_users_count(self, groups):
        with app.app_context():
            return (
                r.table("users")
                .get_all(r.args(groups), index="group")
                .count()
                .run(db.conn)
            )

    def check_secondary_groups_category(self, category, secondary_groups):
        for group in secondary_groups:
            group = self.GroupGet(group)
            if group["parent_category"] != category:
                category = self.CategoryGet(category)["name"]
                raise Error(
                    "forbidden",
                    "Group "
                    + group["name"]
                    + " does not belong to category "
                    + category,
                    traceback.format_exc(),
                )


"""
PASSWORDS MANAGER
"""
import random
import string

import bcrypt


class Password(object):
    def __init__(self):
        None

    def valid(self, plain_password, enc_password):
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), enc_password.encode("utf-8")
        )

    def encrypt(self, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def generate_human(self, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))
