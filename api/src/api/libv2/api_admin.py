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


from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import csv
import io
import os
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from isardvdi_common.api_exceptions import Error

from .api_desktop_events import desktops_delete, desktops_start, desktops_stop
from .api_desktops_persistent import ApiDesktopsPersistent
from .api_templates import ApiTemplates
from .api_user_storage import (
    isard_user_storage_add_category,
    isard_user_storage_add_group,
    isard_user_storage_add_user,
    isard_user_storage_update_category,
    isard_user_storage_update_group,
    isard_user_storage_update_user,
)
from .helpers import _check, get_user_data
from .load_validator_schemas import IsardValidator
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

    if table == "users":
        query = query.without("password")

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
                "desktops_started": r.table("domains")
                .get_all(hyper["id"], index="hyp_started")
                .count(),
            }
        )

    if table == "deployments":
        query = query.merge(
            lambda deploy: {
                "desktop_name": r.table("domains")
                .get_all(deploy["id"], index="tag")["name"][0]
                .default(False),
                "category_name": r.table("users")
                .get(deploy["user"])
                .merge(
                    lambda user: {
                        "category_name": r.table("categories").get(user["category"])[
                            "name"
                        ]
                    }
                )["category_name"]
                .default(False),
                "category": r.table("users")
                .get(deploy["user"])
                .merge(lambda user: {"category": user["category"]})["category"]
                .default(False),
                "group_name": r.table("users")
                .get(deploy["user"])
                .merge(
                    lambda user: {
                        "group_name": r.table("groups").get(user["group"])["name"]
                    }
                )["group_name"]
                .default(False),
                "username": r.table("users")
                .get(deploy["user"])["username"]
                .default(False),
                "co_owners_usernames": r.expr(deploy["co_owners"]).map(
                    lambda co_owner: r.table("users")
                    .get(co_owner)["username"]
                    .default(False)
                ),
                "how_many_desktops": r.table("domains")
                .get_all(deploy["id"], index="tag")
                .count()
                .default(False),
                "how_many_desktops_started": r.table("domains")
                .get_all([deploy["id"], "Started"], index="tag_status")
                .count()
                .default(False),
                "last_access": r.table("domains")
                .get_all(deploy["id"], index="tag")
                .max("accessed")["accessed"]
                .default(False),
            }
        ).default(False)

    if table == "bookings_priority":
        query = query.merge(
            lambda priority: {
                "role_names": r.table("roles")
                .get_all(
                    r.args(
                        r.branch(
                            (priority["allowed"]["roles"] != False),
                            priority["allowed"]["roles"],
                            [],
                        )
                    )
                )["name"]
                .coerce_to("array"),
                "category_names": r.table("categories")
                .get_all(
                    r.args(
                        r.branch(
                            (priority["allowed"]["categories"] != False),
                            priority["allowed"]["categories"],
                            [],
                        )
                    )
                )["name"]
                .coerce_to("array"),
                "group_names": r.table("groups")
                .get_all(
                    r.args(
                        r.branch(
                            (priority["allowed"]["groups"] != False),
                            priority["allowed"]["groups"],
                            [],
                        )
                    )
                )["name"]
                .coerce_to("array"),
                "user_names": r.table("users")
                .get_all(
                    r.args(
                        r.branch(
                            (priority["allowed"]["users"] != False),
                            priority["allowed"]["users"],
                            [],
                        )
                    )
                )["name"]
                .coerce_to("array"),
            }
        )

    if pluck:
        query = query.pluck(pluck)

    if order_by:
        query = query.order_by(order_by)

    if without:
        query = query.without(without)

    if id and not index:
        with app.app_context():
            return query.run(db.conn)
    else:
        with app.app_context():
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
        "desktops_priority",
    ]:
        data = _validate_item(table, data)
        if table == "desktops_priority":
            IsardValidator()._check_with_validate_time_values(data)

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
    if table == "users":
        isard_user_storage_add_user(data["id"])
    if table == "groups":
        isard_user_storage_add_group(data["id"])
    if table == "categories":
        isard_user_storage_add_category(data["id"])


def admin_table_update(table, data, payload=False):
    _validate_table(table)
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

    if table == "users":
        with app.app_context():
            user = (
                r.table("users").get(data["id"]).pluck("name", "category").run(db.conn)
            )
        if not user:
            raise Error(
                "not_found",
                "User not found user_id:" + data["id"],
                traceback.format_exc(),
                description_code="user_not_found",
            )
        with app.app_context():
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
        with app.app_context():
            old_data = r.table("users").get(data["id"]).run(db.conn)
        old_data.update(data)

        isard_user_storage_update_user(
            user_id=data["id"],
            email=data.get("email"),
            displayname=data.get("name"),
            role=data.get("role"),
            enabled=data.get("active"),
        )

        _validate_item("user", old_data)

    if table == "desktops_priority":
        if "allowed" not in data:
            IsardValidator()._check_with_validate_time_values(data)
    if table == "categories":
        isard_user_storage_update_category(data["id"], data["name"])
    if table == "groups":
        isard_user_storage_update_group(data["id"], data["name"])
    if table == "bookings_priority":
        if data["id"] in ["default", "default admins"] and "allowed" in data:
            raise Error(
                "forbidden", "Default priorities' allowed users cannot be modified"
            )
    with app.app_context():
        r.table(table).get(data["id"]).update(data).run(db.conn)


def admin_table_get(table, id, pluck=None):
    _validate_table(table)
    query = r.table(table).get(id)
    if table == "users":
        query = query.without("password")
    if table == "media":
        query = query.merge(
            lambda media: {
                "domains": r.table("domains")
                .get_all(media["id"], index="media_ids")
                .count()
            }
        )
    if pluck:
        if table == "deployments":
            query = query["create_dict"].pluck(pluck)
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


def admin_table_delete_list(table, ids_list, batch_size=50000):
    _validate_table(table)
    for i in range(0, len(ids_list), batch_size):
        batch_ids = ids_list[i : i + batch_size]
        with app.app_context():
            if not _check(
                r.table(table).get_all(r.args(batch_ids)).delete().run(db.conn),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Internal server error",
                    traceback.format_exc(),
                    description_code="generic_error",
                )


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
    def DesktopViewerData(self, desktop_id):
        with app.app_context():
            desktop_viewer = (
                r.table("domains")
                .get(desktop_id)
                .pluck(
                    "guest_properties", "create_dict", {"viewer": {"guest_ip": True}}
                )
                .merge(
                    {
                        "create_dict": {
                            "hardware": {
                                "interfaces": r.row["create_dict"]["hardware"][
                                    "interfaces"
                                ].concat_map(lambda interface: [interface["id"]])
                            }
                        }
                    }
                )
                .run(db.conn)
            )
        return desktop_viewer

    def DeploymentViewerData(self, deployment_id):
        with app.app_context():
            desktop_viewer = (
                r.table("deployments")
                .get(deployment_id)
                .pluck("create_dict")
                .run(db.conn)
            )
        return desktop_viewer

    def DesktopDetailsData(self, desktop_id):
        with app.app_context():
            desktop_viewer = (
                r.table("domains")
                .get(desktop_id)
                .pluck("detail", "description")
                .run(db.conn)
            )
        return desktop_viewer

    def ListDesktops(self, categories=None):
        query = r.table("categories")
        if categories:
            query = query.get_all(r.args(categories))
        query = query.eq_join("id", r.table("groups"), index="parent_category")
        query = query.map(
            lambda doc: {
                "group_id": doc["right"]["id"],
                "group_name": doc["right"]["name"],
                "category_id": doc["left"]["id"],
                "category_name": doc["left"]["name"],
            }
        )
        query = query.eq_join("group_id", r.table("domains"), index="group").filter(
            {"right": {"kind": "desktop"}}
        )
        query = query.merge(
            lambda doc: {
                "right": r.table("users").get(doc["right"]["user"]).pluck("role")
            }
        )
        if categories:
            query.filter(r.row["right"]["category"] in categories)

        query = query.pluck(
            {
                "right": [
                    "id",
                    {
                        "create_dict": {
                            "reservables": True,
                            "hardware": {"vcpus": True, "memory": True},
                        }
                    },
                    {"image": {"url": True}},
                    "kind",
                    "server",
                    "hyp_started",
                    "name",
                    "status",
                    "username",
                    "accessed",
                    "forced_hyp",
                    "favourite_hyp",
                    "booking_id",
                    "role",
                    "persistent",
                    "current_action",
                    "server_autostart",
                ],
                "left": ["group_name", "category_name"],
            }
        ).zip()
        with app.app_context():
            return list(query.run(db.conn))

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
                            .get_all(template_id, index="parents")
                            .count(),
                            "category_name": r.table("categories")
                            .get(domain["category"])["name"]
                            .default(False),
                            "group_name": r.table("groups")
                            .get(domain["group"])["name"]
                            .default(False),
                            "interfaces": domain["create_dict"]["hardware"][
                                "interfaces"
                            ].keys(),
                        }
                    )
                    .run(db.conn)
                )
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error ",
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
                        "status",
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all(domain["id"], index="parents")
                            .distinct()
                            .count(),
                            "category_name": r.table("categories").get(
                                domain["category"]
                            )["name"],
                            "group_name": r.table("groups").get(domain["group"])[
                                "name"
                            ],
                            "interfaces": domain["create_dict"]["hardware"][
                                "interfaces"
                            ].map(lambda interface: interface["id"]),
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

    def domains_status_minimal(self, status):
        with app.app_context():
            return list(
                r.table("domains")
                .get_all(["desktop", status], index="kind_status")
                .pluck(
                    "id",
                    "name",
                    "accessed",
                )
                .run(db.conn)
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

        with app.app_context():
            return list(
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

    # This is the function to be called
    def GetTemplateTreeList(self, template_id, user_id):
        levels = {}
        derivated = self.TemplateTreeList(template_id, user_id)
        for n in derivated:
            levels.setdefault(
                (
                    n["duplicate_parent_template"]
                    if n.get("duplicate_parent_template", False)
                    else n["parent"]
                ),
                [],
            ).append(n)
        recursion = self.TemplateTreeRecursion(template_id, levels)
        with app.app_context():
            user = r.table("users").get(user_id).pluck("id", "role").run(db.conn)
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
                    "duplicate_parent_template",
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
                "unselectable": (
                    False
                    if user["role"] == "manager" or user["role"] == "admin"
                    else True
                ),
                "selected": True if user["id"] == d["user"] else False,
                "parent": (
                    d["parents"][-1]
                    if "parents" in d.keys() and len(d["parents"]) > 0
                    else ""
                ),
                "duplicate_parent_template": d.get("duplicate_parent_template", False),
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

    # Call GetTemplateTreeList. This is a subfunction only.
    def TemplateTreeRecursion(self, template_id, levels):
        nodes = [dict(n) for n in levels.get(template_id, [])]
        for n in nodes:
            children = self.TemplateTreeRecursion(n["id"], levels)
            if children:
                n["children"] = children
        return nodes

    def _derivated(self, template_id):
        with app.app_context():
            return list(
                r.db("isard")
                .table("domains")
                .get_all(template_id, index="parents")
                .pluck(
                    "id",
                    "duplicate_parent_template",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
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

    def _duplicated(self, template_id):
        with app.app_context():
            duplicated_from_original = list(
                r.table("domains")
                .get_all(template_id, index="duplicate_parent_template")
                .pluck(
                    "id",
                    "duplicate_parent_template",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
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

        # Recursively get templates derived from duplicated templates
        derivated_from_duplicated = []
        for d in duplicated_from_original:
            derivated_from_duplicated += self._derivated(d["id"])
        return duplicated_from_original + derivated_from_duplicated

    # This has no recursion. Call GetTemplateTreeList
    def TemplateTreeList(self, template_id, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "role", "category")
                .run(db.conn)
            )

        # Get derivated from this template (and derivated from itself)
        derivated = self._derivated(template_id)

        # Duplicated templates should have the same parent as the original
        # Except for duplicates from root template
        duplicated = self._duplicated(template_id)

        derivated = list(derivated) + list(duplicated)

        if user["role"] == "manager":
            derivated = [
                (
                    {
                        **d,
                        "user": "-",
                        "username": "-",
                        "category": "-",
                        "category_name": "-",
                        "group": "-",
                        "group_name": "-",
                        "unselectable": True,
                        "name": "-",
                    }
                    if d["category"] != user["category"]
                    else d
                )
                for d in derivated
            ]

        fancyd = []
        for d in derivated:
            if user["role"] == "manager" or user["role"] == "admin":
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": (
                            True if not d.get("unselectable") else not d["unselectable"]
                        ),
                        "unselectable": (
                            False if not d.get("unselectable") else d["unselectable"]
                        ),
                        "selected": True if user["id"] == d["user"] else False,
                        "parent": (
                            d["parents"][-1]
                            if d.get("parents")
                            else d["duplicate_parent_template"]
                        ),
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": (
                            "fa fa-desktop" if d["kind"] == "desktop" else "fa fa-cube"
                        ),
                        "duplicate_parent_template": d.get(
                            "duplicate_parent_template", False
                        ),
                    }
                )
            else:
                ## It can only be an advanced user
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": True,
                        "unselectable": False if user["id"] == d["user"] else True,
                        "selected": True if user["id"] == d["user"] else False,
                        "parent": (
                            d["parents"][-1]
                            if d.get("parents")
                            else d["duplicate_parent_template"]
                        ),
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": (
                            "fa fa-desktop" if d["kind"] == "desktop" else "fa fa-cube"
                        ),
                        "duplicate_parent_template": d.get(
                            "duplicate_parent_template", False
                        ),
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

    def MultipleActions(self, table, action, ids, agent_id):
        if action == "soft_toggle":
            domains_stopped = self.CheckField(
                table, "status", "Stopped", ids
            ) + self.CheckField(table, "status", "Failed", ids)
            desktops_start(domains_stopped)
            domains_started = self.CheckField(table, "status", "Started", ids)
            with app.app_context():
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
                with app.app_context():
                    r.table(table).get(domain_id).update(
                        {"tag_visible": True, "jumperurl": self.api_jumperurl_gencode()}
                    ).run(db.conn)
            desktops_stop(domains_shown, force=True)
            with app.app_context():
                res_hidden = (
                    r.table(table)
                    .get_all(r.args(domains_shown))
                    .update({"tag_visible": False, "viewer": False, "jumperurl": False})
                    .run(db.conn)
                )
            return True

        if action == "download_jumperurls":
            with app.app_context():
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
            with app.app_context():
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
            desktops_delete(agent_id, ids)
            return True

        if action == "force_failed":
            with app.app_context():
                res = r.table(table).get_all(r.args(ids)).pluck("status").run(db.conn)
            for item in res:
                if item.get("status") in [
                    "Stopped",
                    "Started",
                    "Downloading",
                ]:
                    return "Cannot change to Failed status desktops from Stopped, Started or Downloading status"
            with app.app_context():
                res_deleted = (
                    r.table(table)
                    .get_all(r.args(ids))
                    .update({"status": "Failed", "hyp_started": False})
                    .run(db.conn)
                )
            return True

        if action == "shutting_down":
            domains_started = self.CheckField(table, "status", "Started", ids)
            with app.app_context():
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

        if action == "activate_autostart":
            with app.app_context():
                r.table("domains").get_all(r.args(ids)).filter({"server": True}).update(
                    {"server_autostart": True}
                ).run(db.conn)
            return True

        if action == "deactivate_autostart":
            with app.app_context():
                r.table("domains").get_all(r.args(ids)).update(
                    {"server_autostart": False}
                ).run(db.conn)
            return True

        return False

    def CheckField(self, table, field, value, ids):
        with app.app_context():
            return list(
                r.table(table)
                .get_all(r.args(ids))
                .filter({field: value})
                .pluck("id")["id"]
                .run(db.conn)
            )

    def get_domains_field(self, field, kind, payload):
        query = r.table("domains")

        if payload["role_id"] == "manager" and kind:
            query = query.get_all([kind, payload["category_id"]], index="kind_category")
        elif payload["role_id"] == "admin" and kind:
            query = query.get_all(kind, index="kind")
        elif payload["role_id"] == "manager" and not kind:
            query = query.get_all(payload["category_id"], index="category")

        if field not in ["vcpus", "memory"]:
            pluck = field
        else:
            pluck = {"create_dict": {"hardware": field}}
        query = query.pluck(pluck)

        query = (
            query["create_dict"]["hardware"] if field in ["vcpus", "memory"] else query
        )
        query = (
            query.map(lambda value: {"memory": (value["memory"] / 1048576)})
            if field == "memory"
            else query
        )

        with app.app_context():
            result = query.distinct().run(db.conn)
        return result

    def set_logs_desktops_old_entries_max_time(self, max_time):
        with app.app_context():
            r.table("config").update(
                {"logs_desktops": {"old_entries": {"max_time": max_time}}}
            ).run(db.conn)

    def set_logs_desktops_old_entries_action(self, action):
        if action == "none":
            with app.app_context():
                r.table("config").replace(
                    r.row.without({"logs_desktops": "old_entries"})
                ).run(db.conn)
        else:
            with app.app_context():
                r.table("config").update(
                    {"logs_desktops": {"old_entries": {"action": action}}}
                ).run(db.conn)

    def get_logs_desktops_old_entries_config(self):
        try:
            with app.app_context():
                return r.table("config")[0]["logs_desktops"]["old_entries"].run(db.conn)
        except r.ReqlNonExistenceError:
            return {"max_time": None, "action": None}

    def set_logs_users_old_entries_max_time(self, max_time):
        with app.app_context():
            r.table("config").update(
                {"logs_users": {"old_entries": {"max_time": max_time}}}
            ).run(db.conn)

    def set_logs_users_old_entries_action(self, action):
        if action == "none":
            with app.app_context():
                r.table("config").replace(
                    r.row.without({"logs_users": "old_entries"})
                ).run(db.conn)
        else:
            with app.app_context():
                r.table("config").update(
                    {"logs_users": {"old_entries": {"action": action}}}
                ).run(db.conn)

    def get_logs_users_old_entries_config(self):
        try:
            with app.app_context():
                return r.table("config")[0]["logs_users"]["old_entries"].run(db.conn)
        except r.ReqlNonExistenceError:
            return {"max_time": None, "action": None}

    def get_older_than_old_entry_max_time(self, table, max_time_config=None):
        if table == "logs_desktops":
            if max_time_config is None:
                max_time_config = self.get_logs_desktops_old_entries_config()[
                    "max_time"
                ]
        elif table == "logs_users":
            if max_time_config is None:
                max_time_config = self.get_logs_users_old_entries_config()["max_time"]
        else:
            raise Error(
                "forbidden",
                "Table not allowed to delete old entries",
                traceback.format_exc(),
            )

        if max_time_config is None:
            raise Error(
                "precondition_required",
                "Max time is not set",
                traceback.format_exc(),
            )

        max_time_hours = int(max_time_config)

        query = r.table(table)

        if table == "logs_desktops":
            query = query.filter(
                (
                    (r.row.has_fields("stopped_time"))
                    & (
                        r.row["stopped_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("stopping_time"))
                    & (
                        r.row["stopping_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("started_time"))
                    & (
                        r.row["started_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("starting_time"))
                    & (
                        r.row["starting_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
            )
        elif table == "logs_users":
            query = query.filter(
                (
                    (r.row.has_fields("stopped_time"))
                    & (
                        r.row["stopped_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("started_time"))
                    & (
                        r.row["started_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
            )

        query = query.pluck("id")["id"]

        with app.app_context():
            return list(query.run(db.conn))


def prrint(*args):
    print(args)
    return args


def admin_table_update_book(table, id, data):
    _validate_table(table)

    with app.app_context():
        r.table(table).get(id).update(data).run(db.conn)
