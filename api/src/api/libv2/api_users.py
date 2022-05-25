#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import logging as log
import pprint
import time
from datetime import datetime, timedelta

from rethinkdb import RethinkDB

from api import app

from .api_exceptions import Error

r = RethinkDB()
import logging
import traceback
from string import ascii_lowercase, digits

from rethinkdb.errors import ReqlNonExistenceError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


from .apiv2_exc import *
from .ds import DS
from .helpers import (
    _check,
    _disk_path,
    _parse_desktop,
    _parse_media_info,
    _parse_string,
    _random_password,
)

ds = DS()

import os
import secrets

import bcrypt
import requests
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
    return not allowed_domain or domain == allowed_domain


class ApiUsers:
    def Jwt(self, user_id, minutes=240):
        # user_id = provider_id+'-'+category_id+'-'+id+'-'+id
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck(
                        "id", "username", "photo", "email", "role", "category", "group"
                    )
                    .run(db.conn)
                )
                user = {
                    "user_id": user["id"],
                    "role_id": user["role"],
                    "category_id": user["category"],
                    "group_id": user["group"],
                    "username": user["username"],
                    "email": user["email"],
                    "photo": user["photo"],
                }
        except:
            raise Error(
                "not_found", "Not found user_id " + user_id, traceback.format_exc()
            )
        return {
            "jwt": jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(minutes=minutes),
                    "kid": "isardvdi",
                    "data": user,
                },
                app.ram["secrets"]["isardvdi"]["secret"],
                algorithm="HS256",
            )
        }

    def Login(self, user_id, user_passwd, provider="local", category_id="default"):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if user is None:
            raise Error("unauthorized", "", traceback.format_stack())
        if not user.get("active", False):
            raise Error(
                "unauthorized",
                "User " + user_id + " is disabled",
                traceback.format_stack(),
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
            traceback.format_stack(),
        )

    def Get(self, user_id):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if not user:
            raise Error(
                "not_found", "Not found user_id " + user_id, traceback.format_stack()
            )
        return user

    def List(self):
        with app.app_context():
            return list(
                r.table("users")
                .without("password", {"vpn": {"wireguard": "keys"}})
                .merge(
                    lambda user: {
                        "desktops": r.table("domains")
                        .get_all(user["id"], index="user")
                        .filter({"kind": "desktop"})
                        .count(),
                        "templates": r.table("domains")
                        .get_all(user["id"], index="user")
                        .filter({"kind": "template"})
                        .count(),
                    }
                )
                .run(db.conn)
            )

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
                    traceback.format_stack(),
                )

            if r.table("roles").get(role_id).run(db.conn) is None:
                raise Error(
                    "not_found",
                    "Not found role_id " + role_id + " for user_id " + user_id,
                    traceback.format_stack(),
                )

            if r.table("categories").get(category_id).run(db.conn) is None:
                raise Error(
                    "not_found",
                    "Not found category_id " + category_id + " for user_id " + user_id,
                    traceback.format_stack(),
                )

            group = r.table("groups").get(group_id).run(db.conn)
            if group is None:
                raise Error(
                    "not_found",
                    "Not found group_id " + group_id + " for user_id " + user_id,
                    traceback.format_stack(),
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
                "accessed": time.time(),
                "username": user_username,
                "password": password,
                "role": role_id,
                "category": category_id,
                "group": group_id,
                "email": email,
                "photo": photo,
                "default_templates": [],
                "quota": group["quota"],  # 10GB
            }
            if not _check(r.table("users").insert(user).run(db.conn), "inserted"):
                raise Error(
                    "internal_server",
                    "Unable to insert in database user_id " + user_id,
                    traceback.format_stack(),
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
                        traceback.format_stack(),
                    )

    def Templates(self, payload):
        try:
            with app.app_context():
                templates = (
                    r.table("domains")
                    .get_all("template", index="kind")
                    .filter({"enabled": True})
                    .order_by("name")
                    .pluck(
                        {
                            "id",
                            "name",
                            "allowed",
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
            alloweds = []
            for template in templates:
                try:
                    with app.app_context():
                        template["username"] = (
                            r.table("users")
                            .get(template["user"])
                            .pluck("name")
                            .run(db.conn)["name"]
                        )
                except:
                    template["username"] = "X " + template["user"]
                template["editable"] = False
                # with app.app_context():
                #     desktop['username']=r.table('users').get(desktop['user']).pluck('name').run(db.conn)['name']
                if payload["role_id"] == "admin":
                    template["editable"] = True
                    alloweds.append(template)
                    continue
                if (
                    payload["role_id"] == "manager"
                    and payload["category_id"] == template["category"]
                ):
                    template["editable"] = True
                    alloweds.append(template)
                    continue
                if not payload.get("user_id", False):
                    continue
                if template["user"] == payload["user_id"]:
                    template["editable"] = True
                    alloweds.append(template)
                    continue
                if template["allowed"]["roles"] is not False:
                    if len(template["allowed"]["roles"]) == 0:
                        alloweds.append(template)
                        continue
                    else:
                        if payload["role_id"] in template["allowed"]["roles"]:
                            alloweds.append(template)
                            continue
                if template["allowed"]["categories"] is not False:
                    if len(template["allowed"]["categories"]) == 0:
                        alloweds.append(template)
                        continue
                    else:
                        if payload["category_id"] in template["allowed"]["categories"]:
                            alloweds.append(template)
                            continue
                if template["allowed"]["groups"] is not False:
                    if len(template["allowed"]["groups"]) == 0:
                        alloweds.append(template)
                        continue
                    else:
                        if payload["group_id"] in template["allowed"]["groups"]:
                            alloweds.append(template)
                            continue
                if template["allowed"]["users"] is not False:
                    if len(template["allowed"]["users"]) == 0:
                        alloweds.append(template)
                        continue
                    else:
                        if payload["user_id"] in template["allowed"]["users"]:
                            alloweds.append(template)
                            continue
            return alloweds
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
                    .get_all(user_id, index="user")
                    .filter({"kind": "desktop"})
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
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {"create_dict": {"hardware": ["interfaces", "videos"]}},
                            "progress",
                        ]
                    )
                    .run(db.conn)
                )
            return [
                _parse_desktop(desktop)
                for desktop in desktops
                if desktop.get("tag_visible", True)
            ]
        except Exception:
            raise Error(
                "internal_server", "Internal server error", traceback.format_exc()
            )

    def Desktop(self, desktop_id, user_id):
        self.Get(user_id)
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
                        "tag_visible",
                        {"viewer": "guest_ip"},
                        {"create_dict": {"hardware": ["interfaces", "videos"]}},
                    ]
                )
                .default(None)
                .run(db.conn)
            )
        if not desktop:
            raise Error(
                "not_found",
                "Not found desktop_id " + desktop_id + " for user_id " + user_id,
                traceback.format_exc(),
            )

        try:
            # Modify desktop data to be returned
            if desktop.get("tag_visible", True):

                # if desktop["status"] not in ["Started", "Failed","Stopped"]:
                #     desktop["status"] = "Working"
                desktop["image"] = desktop.get("image", None)
                desktop["from_template"] = desktop.get("parents", [None])[-1]
                if desktop.get("persistent", True):
                    desktop["type"] = "persistent"
                else:
                    desktop["type"] = "nonpersistent"
                desktop["viewers"] = ["file-spice", "browser-vnc"]
                if desktop["status"] == "Started":
                    if "wireguard" in desktop["create_dict"]["hardware"]["interfaces"]:
                        desktop["ip"] = desktop.get("viewer", {}).get("guest_ip")
                        if not desktop["ip"]:
                            desktop["status"] = "WaitingIP"
                        if desktop["os"].startswith("win"):
                            desktop["viewers"].extend(
                                ["file-rdpgw", "file-rdpvpn", "browser-rdp"]
                            )
                return desktop
            else:
                return None
        except Exception:
            raise Error(
                "internal_server",
                "Get desktop failed for user_id " + user_id,
                traceback.format_exc(),
            )

    def Delete(self, user_id):
        self.Get(user_id)
        todelete = self._user_delete_checks(user_id)
        for desktop in todelete:
            ds.delete_desktop(desktop["id"], desktop["status"])

        # self._delete_non_persistent(user_id)
        with app.app_context():
            if not _check(
                r.table("users").get(user_id).delete().run(db.conn), "deleted"
            ):
                raise Error(
                    "internal_server",
                    "Unable to delete user_id " + user_id,
                    traceback.format_stack(),
                )

    def _user_delete_checks(self, user_id):
        with app.app_context():
            user_desktops = list(
                r.table("domains")
                .get_all(user_id, index="user")
                .filter({"kind": "desktop"})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            user_templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .filter({"user": user_id})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            derivated = []
            for ut in user_templates:
                id = ut["id"]
                derivated = derivated + list(
                    r.table("domains")
                    .pluck("id", "name", "kind", "user", "status", "parents")
                    .filter(lambda derivates: derivates["parents"].contains(id))
                    .run(db.conn)
                )
                # templates = [t for t in derivated if t['kind'] != "desktop"]
                # desktops = [d for d in derivated if desktop['kind'] == "desktop"]
        domains = user_desktops + user_templates + derivated
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
            "forbidden", "Forbidden access to desktop viewer", traceback.format_stack()
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
            "not_found", "Code not found code:" + code, traceback.format_stack()
        )

    def CategoryGet(self, category_id, all=False):
        with app.app_context():
            category = r.table("categories").get(category_id).run(db.conn)
        if not category:
            raise Error(
                "not_found",
                "Category not found category_id:" + category_id,
                traceback.format_stack(),
            )
        if not all:
            return {"name": category["name"]}
        else:
            return category

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
            if category == None:
                return []
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
                .get_all(category_id, index="category")
                .filter({"kind": "desktop"})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            category_templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .filter({"category": category_id})
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
                # templates = [t for t in derivated if t['kind'] != "desktop"]
                # desktops = [d for d in derivated if d['kind'] == "desktop"]
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
        with app.app_context():
            try:
                for d in self.category_delete_checks(category_id):
                    if d["kind"] == "user":
                        r.table("users").get(d["id"]).delete().run(db.conn)
                    elif d["kind"] == "group":
                        r.table("groups").get(d["id"]).delete().run(db.conn)
                    elif d["kind"] == "category":
                        r.table("categories").get(d["id"]).delete().run(db.conn)
                    else:
                        ds.delete_desktop(d["id"], d["status"])

            except Exception as e:
                print(traceback.format_exc())
                raise Error(
                    "not_found",
                    "Error deleting category " + category_id + "and related items. \n",
                    traceback.format_stack(),
                )

    def GroupGet(self, group_id):
        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
        if not group:
            raise Error(
                "not_found", "Not found group_id " + group_id, traceback.format_exc()
            )
        return group

    def GroupsGet(self):
        return list(r.table("groups").order_by("name").run(db.conn))

    def group_delete_checks(self, group_id):
        with app.app_context():
            try:
                group = r.table("groups").get(group_id).pluck("id", "name").run(db.conn)
            except:
                return []
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

            deployment_desktops = list(
                r.table("domains")
                .get_all(group_id, index="group")
                .filter({"kind": "desktop"})
                .pluck("id", "name", "kind", "user", "status", "parents")
                .run(db.conn)
            )
            group_templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .filter({"group": group_id})
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
                # templates = [t for t in derivated if t['kind'] != "desktop"]
                # desktops = [d for d in derivated if d['kind'] == "desktop"]
        domains = groups + users + deployment_desktops + group_templates + derivated
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
            raise Error("not_found", "Group id " + str(group_id) + " not found")

        desktops = (
            r.table("domains")
            .filter({"category": category})
            .pluck("id", "status")
            .run(db.conn)
        )

        for desktop in desktops:
            ds.delete_desktop(desktop["id"], desktop["status"])

        with app.app_context():
            try:
                for d in self.group_delete_checks(group_id):
                    if d["kind"] == "user":
                        r.table("users").get(d["id"]).delete().run(db.conn)
                    elif d["kind"] == "group":
                        r.table("groups").get(d["id"]).delete().run(db.conn)
                    else:
                        ds.delete_desktop(d["id"], d["status"])
            except Exception as e:
                raise Error(
                    "not_found",
                    "Error deleting group and related items. " + group_id,
                    traceback.format_exc(),
                )

    def Secret(self, kid, description, role_id, category_id, domain):
        with app.app_context():
            ## TODO: Check if exists, check that role is correct and category exists
            secret = secrets.token_urlsafe(32)
            r.table("secrets").insert(
                {
                    "id": kid,
                    "secret": secret,
                    "description": description,
                    "role_id": role_id,
                    "category_id": category_id,
                    "domain": domain,
                }
            ).run(db.conn)
        return secret

    def SecretDelete(self, kid):
        with app.app_context():
            ## TODO: Check if exists, check that role is correct and category exists
            secret = secrets.token_urlsafe(32)
            r.table("secrets").get(kid).delete().run(db.conn)
        return True

    def EnrollmentAction(self, data):
        if data["action"] == "disable":
            with app.app_context():
                r.table("groups").get(data["group_id"]).update(
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
                    r.table("groups").get(data["group_id"]).update(
                        {"enrollment": {data["role"]: code}}
                    ).run(db.conn)
                return code
        return False

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

    def UpdateQuota(self, id, quota, table, kind):
        with app.app_context():
            r.table(table).get(id).update({kind: quota}).run(db.conn)


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
