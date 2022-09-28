#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3


from rethinkdb import RethinkDB

from api import app

from .api_exceptions import Error

r = RethinkDB()
import csv
import io
import time
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.authentication import *
from .api_desktops_persistent import ApiDesktopsPersistent
from .api_exceptions import Error
from .api_templates import ApiTemplates
from .helpers import _check, _parse_string, get_user_data
from .validators import _validate_item, _validate_table


def admin_table_list(
    table, order_by=None, pluck=None, without=None, id=None, index=None
):
    _validate_table(table)

    query = r.table(table)

    if id and not index:
        query = query.get(id)
    elif id and index:
        query = query.get_all(id, index=index)

    if table == "media":
        query = query.merge(
            lambda media: {
                "domains": r.table("domains")
                .get_all(media["id"], index="media_ids")
                .count()
            }
        )

    if table == "hypervisors":
        query = query.merge(
            lambda hyper: {
                "gpus": r.table("vgpus").filter({"hyp_id": hyper["id"]}).count(),
                "dom_started": r.table("domains")
                .get_all(hyper["id"], index="hyp_started")
                .count(),
            }
        )

    if pluck:
        query = query.pluck(pluck)

    if order_by:
        query = query.order_by(order_by)

    if without:
        query = query.without(without)

    if table == "groups":
        query = query.merge(
            lambda group: {
                "linked_groups_data": r.table("groups")
                .get_all(r.args(group["linked_groups"]))
                .pluck("id", "name")
                .coerce_to("array"),
            }
        )

    with app.app_context():
        if id and not index:
            return query.run(db.conn)
        else:
            return list(query.run(db.conn))


def admin_table_insert(table, data):
    if data["id"] == None:
        data["id"] = _parse_string(data["name"])
    _validate_table(table)
    if table == "interfaces":
        _validate_item(table, data)
    with app.app_context():
        if r.table(table).get(data["id"]).run(db.conn) == None:
            if not _check(r.table(table).insert(data).run(db.conn), "inserted"):
                raise Error(
                    "internal_server",
                    "Internal server error ",
                    traceback.format_exc(),
                )
        else:
            raise Error(
                "conflict", "Id " + data["id"] + " already exists in table " + table
            )


def admin_table_update(table, data):
    _validate_table(table)
    if table == "interfaces":
        _validate_item(table, data)
    if table == "hypervisors":
        if data.get("capabilities"):
            if not data["capabilities"].get("hypervisor") and not data[
                "capabilities"
            ].get("disk_operations"):
                raise Error(
                    "bad_request",
                    "'disk_operations' and 'hypervisor' capabilities can't be both false",
                    traceback.format_exc(),
                )

    with app.app_context():
        if table == "users":
            old_data = r.table("users").get(data["id"]).run(db.conn)
            old_data.update(data)
            _validate_item("user", old_data)
        if not _check(
            r.table(table).get(data["id"]).update(data).run(db.conn),
            "replaced",
        ):
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
            )


def admin_table_get(table, id, pluck=None):
    _validate_table(table)
    query = r.table(table).get(id)
    if table == "media":
        query = query.merge(
            lambda media: {
                "domains": r.table("domains")
                .get_all(media["id"], index="media_ids")
                .count()
            }
        )
    if pluck:
        query = query.pluck(pluck)
    with app.app_context():
        return query.run(db.conn)


def admin_table_delete(table, item_id):
    _validate_table(table)
    with app.app_context():
        if r.table(table).get(item_id).run(db.conn):
            if not _check(
                r.table(table).get(item_id).delete().run(db.conn),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Internal server error",
                    traceback.format_exc(),
                    description_code="generic_error",
                )
        else:
            raise Error(
                "not_found",
                "Item " + str(item_id) + " not found",
                description_code="not_found",
            )


def admin_domains_delete(list):
    [ApiDesktopsPersistent().Delete(d["id"]) for d in list if d["kind"] == "desktop"]
    [ApiTemplates().Delete(d["id"]) for d in list if d["kind"] == "template"]


## CHANGE ITEMS OWNER
def change_user_items_owner(table, user_id, new_user_id="admin"):
    if table not in ["media"]:
        raise Error(
            "forbidden",
            "Table not allowed to change owner",
            traceback.format_exc(),
        )
    with app.app_context():
        r.table(table).get_all(user_id, index="user").update(
            get_user_data(new_user_id)
        ).run(db.conn)


def change_group_items_owner(table, group_id, new_user_id="admin"):
    if table not in ["media"]:
        raise Error(
            "forbidden",
            "Table not allowed to change owner",
            traceback.format_exc(),
        )
    with app.app_context():
        r.table(table).get_all(group_id, index="group").update(
            get_user_data(new_user_id)
        ).run(db.conn)


def change_category_items_owner(table, category_id, new_user_id="admin"):
    if table not in ["media"]:
        raise Error(
            "forbidden",
            "Table not allowed to change owner",
            traceback.format_exc(),
        )
    with app.app_context():
        r.table(table).get_all(category_id, index="category").update(
            get_user_data(new_user_id)
        ).run(db.conn)


def change_item_owner(table, item_id, new_user_id="admin"):
    if table not in ["media"]:
        raise Error(
            "forbidden",
            "Table not allowed to change owner",
            traceback.format_exc(),
        )
    with app.app_context():
        r.table(table).get(item_id).update(get_user_data(new_user_id)).run(db.conn)


class ApiAdmin:
    def ListDesktops(self, user_id):
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) == None:
                raise Error(
                    "not_found",
                    "Not found user_id " + user_id,
                    traceback.format_exc(),
                )
        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all("desktop", index="kind")
                    .order_by("name")
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "server",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "status",
                        "user",
                        "username",
                        "category",
                        "group",
                        "accessed",
                        "detail",
                        {"viewer": "guest_ip"},
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "disk_bus": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                        "forced_hyp",
                        "os",
                        "guest_properties",
                    )
                    .run(db.conn)
                )
            return domains
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error " + user_id,
                traceback.format_exc(),
            )

    def GetTemplate(self, template_id):
        try:
            with app.app_context():
                return (
                    r.table("domains")
                    .get(template_id)
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "username",
                        "category",
                        "group",
                        "enabled",
                        "derivates",
                        "accessed",
                        "detail",
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "forced_hyp": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all([1, template_id], index="parents")
                            .distinct()
                            .count()
                        }
                    )
                    .order_by("name")
                    .run(db.conn)
                )
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error " + user_id,
                traceback.format_exc(),
            )

    def ListTemplates(self, user_id):
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) == None:
                raise Error(
                    "not_found",
                    "Not found user_id " + user_id,
                    traceback.format_exc(),
                )

        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all("template", index="kind")
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "username",
                        "category",
                        "group",
                        "enabled",
                        "derivates",
                        "accessed",
                        "detail",
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "forced_hyp": True,
                                    "disk_bus": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all([1, domain["id"]], index="parents")
                            .distinct()
                            .count()
                        }
                    )
                    .order_by("name")
                    .run(db.conn)
                )
            return domains
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error " + user_id,
                traceback.format_exc(),
            )

    def GetTemplateTreeList(self, template_id, user_id):
        levels = {}
        derivated = self.TemplateTreeList(template_id, user_id)
        for n in derivated:
            levels.setdefault(n["parent"], []).append(n)
        recursion = self.TemplateTreeRecursion(template_id, levels)
        with app.app_context():
            user_id = r.table("users").get(user_id).run(db.conn)
            d = (
                r.table("domains")
                .get(template_id)
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "category_name",
                    "group",
                    "group_name",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .run(db.conn)
            )
        root = [
            {
                "id": d["id"],
                "title": d["name"],
                "expanded": True,
                "unselectable": False
                if user_id["role"] == "manager" or user_id["role"] == "admin"
                else True,
                "selected": True if user_id["id"] == d["user"] else False,
                "parent": d["parents"][-1]
                if "parents" in d.keys() and len(d["parents"]) > 0
                else "",
                "user": d["username"],
                "category": d["category_name"],
                "group": d["group_name"],
                "kind": d["kind"] if d["kind"] == "desktop" else "template",
                "status": d["status"],
                "icon": "fa fa-desktop" if d["kind"] == "desktop" else "fa fa-cube",
                "children": recursion,
            }
        ]
        return root

    def TemplateTreeRecursion(self, template_id, levels):
        nodes = [dict(n) for n in levels.get(template_id, [])]
        for n in nodes:
            children = self.TemplateTreeRecursion(n["id"], levels)
            if children:
                n["children"] = children
            for c in children:
                if c["unselectable"] == True:
                    n["unselectable"] = True
                    break
        return nodes

    def TemplateTreeList(self, template_id, user_id):
        with app.app_context():
            user_id = r.table("users").get(user_id).run(db.conn)
            template = (
                r.table("domains")
                .get(template_id)
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "category_name",
                    "group",
                    "group_name",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .run(db.conn)
            )
            derivated = list(
                r.db("isard")
                .table("domains")
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .filter(lambda derivates: derivates["parents"].contains(template_id))
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .run(db.conn)
            )
        if user_id["role"] == "manager":
            if template["category"] != user_id["category"]:
                return []
            derivated = [d for d in derivated if d["category"] == user_id["category"]]
        fancyd = []
        for d in derivated:
            if user_id["role"] == "manager" or user_id["role"] == "admin":
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": True,
                        "unselectable": False,
                        "selected": True if user_id["id"] == d["user"] else False,
                        "parent": d["parents"][-1],
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": "fa fa-desktop"
                        if d["kind"] == "desktop"
                        else "fa fa-cube",
                    }
                )
            else:
                ## It can only be an advanced user
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": True,
                        "unselectable": False if user_id["id"] == d["user"] else True,
                        "selected": True if user_id["id"] == d["user"] else False,
                        "parent": d["parents"][-1],
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": "fa fa-desktop"
                        if d["kind"] == "desktop"
                        else "fa fa-cube",
                    }
                )
        return fancyd

    def TemplatesByTerm(self, term):
        with app.app_context():
            data = (
                r.table("domains")
                .get_all("template", index="kind")
                .filter(r.row["name"].match(term))
                .order_by("name")
                .pluck(
                    {
                        "id",
                        "name",
                        "kind",
                        "group",
                        "icon",
                        "user",
                        "description",
                        "category",
                    }
                )
                .run(db.conn)
            )
        return data

    def MultipleActions(self, table, action, ids):
        with app.app_context():
            if action == "soft_toggle":
                domains_stopped = self.CheckField(
                    table, "status", "Stopped", ids
                ) + self.CheckField(table, "status", "Failed", ids)
                domains_started = self.CheckField(table, "status", "Started", ids)
                res_stopped = (
                    r.table(table)
                    .get_all(r.args(domains_stopped))
                    .update({"status": "Starting", "accessed": int(time.time())})
                    .run(db.conn)
                )
                res_started = (
                    r.table(table)
                    .get_all(r.args(domains_started))
                    .update({"status": "Shutting-down"})
                    .run(db.conn)
                )
                return True

            if action == "toggle":
                domains_stopped = self.CheckField(
                    table, "status", "Stopped", ids
                ) + self.CheckField(table, "status", "Failed", ids)
                domains_started = self.CheckField(table, "status", "Started", ids)
                res_stopped = (
                    r.table(table)
                    .get_all(r.args(domains_stopped))
                    .update({"status": "Starting", "accessed": int(time.time())})
                    .run(db.conn)
                )
                res_started = (
                    r.table(table)
                    .get_all(r.args(domains_started))
                    .update({"status": "Stopping", "accessed": int(time.time())})
                    .run(db.conn)
                )
                return True

            if action == "toggle_visible":
                domains_shown = self.CheckField(table, "tag_visible", True, ids)
                domains_hidden = self.CheckField(table, "tag_visible", False, ids)
                for domain_id in domains_hidden:
                    r.table(table).get(domain_id).update(
                        {"tag_visible": True, "jumperurl": self.api_jumperurl_gencode()}
                    ).run(db.conn)
                res_hidden = (
                    r.table(table)
                    .get_all(r.args(domains_shown))
                    .filter({"status": "Started"})
                    .update({"status": "Stopping", "accessed": int(time.time())})
                    .run(db.conn)
                )
                res_hidden = (
                    r.table(table)
                    .get_all(r.args(domains_shown))
                    .update({"tag_visible": False, "viewer": False, "jumperurl": False})
                    .run(db.conn)
                )
                return True

            if action == "download_jumperurls":
                data = list(
                    r.table(table)
                    .get_all(r.args(ids))
                    .pluck("id", "user", "jumperurl")
                    .has_fields("jumperurl")
                    .run(db.conn)
                )
                data = [d for d in data if d["jumperurl"]]
                if not len(data):
                    return "username,name,email,url"
                users = list(
                    r.table("users")
                    .get_all(r.args([u["user"] for u in data]))
                    .pluck("id", "username", "name", "email")
                    .run(db.conn)
                )
                result = []
                for d in data:
                    u = [u for u in users if u["id"] == d["user"]][0]
                    result.append(
                        {
                            "username": u["username"],
                            "name": u["name"],
                            "email": u["email"],
                            "url": "https://"
                            + os.environ["DOMAIN"]
                            + "/vw/"
                            + d["jumperurl"],
                        }
                    )

                fieldnames = ["username", "name", "email", "url"]
                with io.StringIO() as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in result:
                        writer.writerow(row)
                    return csvfile.getvalue()
                return data

            if action == "delete":
                domains_deleting = self.CheckField(table, "status", "Deleting", ids)
                res = (
                    r.table(table)
                    .get_all(r.args(domains_deleting))
                    .delete()
                    .run(db.conn)
                )
                domains = list(
                    r.table(table)
                    .get_all(r.args(ids))
                    .pluck("id", "status")
                    .run(db.conn)
                )
                domains = [
                    d["id"]
                    for d in domains
                    if d["status"]
                    in [
                        "Stopped",
                        "Disabled",
                        "Failed",
                        "Creating",
                        "CreatingDisk",
                        "CreatingAndStarting",
                        "Shutting-down",
                    ]
                ]
                res = (
                    r.table(table)
                    .get_all(r.args(domains))
                    .update({"status": "Deleting"})
                    .run(db.conn)
                )
                return True

            if action == "force_failed":
                res = r.table(table).get_all(r.args(ids)).pluck("status").run(db.conn)
                for item in res:
                    if item.get("status") in ["Stopped", "Started", "Downloading"]:
                        return "Cannot change to Failed status desktops from Stopped, Started or Downloading status"
                res_deleted = (
                    r.table(table)
                    .get_all(r.args(ids))
                    .update({"status": "Failed"})
                    .run(db.conn)
                )
                return True

            if action == "shutting_down":
                domains_started = self.CheckField(table, "status", "Started", ids)
                res_deleted = (
                    r.table(table)
                    .get_all(r.args(domains_started))
                    .update({"status": "Shutting-down"})
                    .run(db.conn)
                )
                return True

            if action == "stopping":
                domains_shutting_down = self.CheckField(
                    table, "status", "Shutting-down", ids
                )
                domains_started = self.CheckField(table, "status", "Started", ids)
                domains = domains_shutting_down + domains_started
                res_deleted = (
                    r.table(table)
                    .get_all(r.args(domains))
                    .update({"status": "Stopping", "accessed": int(time.time())})
                    .run(db.conn)
                )
                return True

                ## TODO: Pending Stats
            # if action == "stop_noviewer":
            #     domains_tostop = self.CheckField(
            #         table, "status", "Started", ids
            #     )
            #     res = (
            #         r.table(table)
            #         .get_all(r.args(domains_tostop))
            #         .filter(~r.row.has_fields({"viewer": "client_since"}))
            #         .update({"status": "Stopping","accessed":int(time.time())})
            #         .run(db.conn)
            #     )
            #     return True

            if action == "starting_paused":
                domains_stopped = self.CheckField(table, "status", "Stopped", ids)
                domains_failed = self.CheckField(table, "status", "Failed", ids)
                domains = domains_stopped + domains_failed
                res = (
                    r.table(table)
                    .get_all(r.args(domains))
                    .update({"status": "StartingPaused", "accessed": int(time.time())})
                    .run(db.conn)
                )
                return True
        return False

    def CheckField(self, table, field, value, ids):
        with app.app_context():
            return [
                d["id"]
                for d in list(
                    r.table(table)
                    .get_all(r.args(ids))
                    .filter({field: value})
                    .pluck("id")
                    .run(db.conn)
                )
            ]


def admin_table_update_book(table, id, data):
    _validate_table(table)

    if not _check(
        r.table(table).get(id).update(data).run(db.conn),
        "replaced",
    ):
        raise UpdateFailed
