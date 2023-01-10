#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3


from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error

r = RethinkDB()
import csv
import io
import time
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .._common.api_exceptions import Error
from .api_desktop_events import desktops_start, desktops_stop
from .api_desktops_persistent import ApiDesktopsPersistent
from .api_templates import ApiTemplates
from .helpers import _check, get_user_data
from .validators import _validate_item, _validate_table


def admin_table_list(
    table, order_by=None, pluck=None, without=None, id=None, index=None, merge=True
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
                .count(),
                "category_name": r.table("categories").get(media["category"])["name"],
                "group_name": r.table("groups").get(media["group"])["name"],
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

    with app.app_context():
        if id and not index:
            return query.run(db.conn)
        else:
            return list(query.run(db.conn))


def admin_table_insert(table, data):
    _validate_table(table)
    if table in [
        "interfaces",
        "graphics",
        "videos",
        "qos_net",
        "qos_disk",
        "remotevpn",
        "bookings_priority",
    ]:
        data = _validate_item(table, data)
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


def admin_table_update(table, data, payload=False):
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
            user = r.table("users").get(data["id"]).run(db.conn)
            if not user:
                raise Error(
                    "not_found",
                    "User not found user_id:" + data["id"],
                    traceback.format_exc(),
                    description_code="user_not_found",
                )
            category = r.table("categories").get(user["category"]).run(db.conn)
            if not category:
                raise Error(
                    "not_found",
                    "Category not found category_id:" + user["category"],
                    traceback.format_exc(),
                    description_code="category_not_found",
                )
            # Managers can't update a user quota with a higher value than its category quota
            if payload["role_id"] == "manager":

                if category["quota"] != False:
                    for k, v in category["quota"].items():
                        if (
                            data.get("quota")
                            and data.get("quota").get(k)
                            and v < data.get("quota")[k]
                        ):
                            raise Error(
                                "precondition_required",
                                "Can't update "
                                + user["name"]
                                + " "
                                + k
                                + " quota value with a higher value than its category quota",
                                traceback.format_exc(),
                            )

            # Can't update a user quota with a higher value than its category limit
            if category["limits"] != False:
                for k, v in category["limits"].items():
                    if (
                        data.get("quota")
                        and data.get("quota").get(k)
                        and v < data.get("quota")[k]
                    ):
                        raise Error(
                            "precondition_required",
                            "Can't update "
                            + data["name"]
                            + " "
                            + k
                            + " quota value with a higher value than its category limit",
                            traceback.format_exc(),
                        )
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
    if table == "users":
        query = query.merge(
            lambda d: {
                "secondary_groups_data": r.table("groups")
                .get_all(r.args(d["secondary_groups"]))
                .pluck("id", "name")
                .coerce_to("array")
            }
        )
    if table == "groups":
        query = query.merge(
            lambda d: {
                "linked_groups_data": r.table("groups")
                .get_all(r.args(d["linked_groups"]))
                .pluck("id", "name")
                .coerce_to("array")
            }
        )
    with app.app_context():
        return query.run(db.conn)


def admin_table_delete(table, item_id):
    _validate_table(table)
    if table in ["interfaces"]:
        query = r.table("domains")
        desktops = query.run(db.conn)
        for desktop in desktops:
            if item_id in desktop["create_dict"]["hardware"]["interfaces"]:
                desktop["create_dict"]["hardware"]["interfaces"].remove(item_id)
                admin_table_update("domains", desktop)
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
                                    "virtualization_nested": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                        "forced_hyp",
                        "favourite_hyp",
                        "os",
                        "guest_properties",
                    )
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
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
                                    "favourite_hyp": True,
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
                            .count(),
                            "category_name": r.table("categories").get(
                                domain["category"]
                            )["name"],
                            "group_name": r.table("groups").get(domain["group"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(domain["group"])[
                                "name"
                            ],
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
                                    "favourite_hyp": True,
                                    "disk_bus": True,
                                    "virtualization_nested": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                        "forced_hyp",
                        "favourite_hyp",
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all([1, domain["id"]], index="parents")
                            .distinct()
                            .count(),
                            "category_name": r.table("categories").get(
                                domain["category"]
                            )["name"],
                            "group_name": r.table("groups").get(domain["group"])[
                                "name"
                            ],
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

    def get_domain_storage(self, domain_id):
        with app.app_context():
            desktop_disks = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "hardware"})["create_dict"]["hardware"]["disks"]
                .run(db.conn)
            )

            storage_ids = []
            for storage in desktop_disks:
                if storage.get("storage_id"):
                    storage_ids.append(storage.get("storage_id"))
            desktop_storage = list(
                r.table("storage")
                .get_all(r.args(storage_ids))
                .merge(
                    lambda storage: {
                        "actual_size": storage["qemu-img-info"]["actual-size"].default(
                            0
                        )
                        / 1073741824,
                        "virtual_size": storage["qemu-img-info"][
                            "virtual-size"
                        ].default(0)
                        / 1073741824,
                    }
                )
                .run(db.conn)
            )
        return desktop_storage

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
                desktops_start(domains_stopped)
                domains_started = self.CheckField(table, "status", "Started", ids)
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
                desktops_start(domains_stopped)
                domains_started = self.CheckField(table, "status", "Started", ids)
                desktops_stop(domains_started, force=True)
                return True

            if action == "toggle_visible":
                domains_shown = self.CheckField(table, "tag_visible", True, ids)
                domains_hidden = self.CheckField(table, "tag_visible", False, ids)
                for domain_id in domains_hidden:
                    r.table(table).get(domain_id).update(
                        {"tag_visible": True, "jumperurl": self.api_jumperurl_gencode()}
                    ).run(db.conn)
                desktops_stop(domains_shown, force=True)
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
                with app.app_context():
                    r.table(table).get_all(r.args(ids)).update(
                        {"status": "ForceDeleting"}
                    ).run(db.conn)
                return True

            if action == "force_failed":
                res = r.table(table).get_all(r.args(ids)).pluck("status").run(db.conn)
                for item in res:
                    if item.get("status") in [
                        "Stopped",
                        "Started",
                        "Downloading",
                    ]:
                        return "Cannot change to Failed status desktops from Stopped, Started or Downloading status"
                res_deleted = (
                    r.table(table)
                    .get_all(r.args(ids))
                    .update({"status": "Failed", "hyp_started": False})
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
                desktops_stop(domains, force=True)
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
                desktops_start(domains, paused=True)
                return True

            if action == "remove_forced_hyper":
                with app.app_context():
                    r.table("domains").get_all(r.args(ids)).update(
                        {"forced_hyp": False}
                    ).run(db.conn)
                return True

            if action == "remove_favourite_hyper":
                with app.app_context():
                    r.table("domains").get_all(r.args(ids)).update(
                        {"favourite_hyp": False}
                    ).run(db.conn)
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
