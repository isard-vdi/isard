#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3


import time

from isardvdi_common.api_exceptions import Error
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.storage import Storage
from isardvdi_common.task import Task
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_notify import notify_admins
from ..libv2.load_validator_schemas import IsardValidator

r = RethinkDB()
import csv
import io
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import logging as log

from isardvdi_common.api_exceptions import Error


def get_status(category_id=None):
    query = r.table("storage").pluck("status", "user_id")
    if category_id:
        query = (
            query.eq_join(
                [r.row["user_id"], category_id], r.table("users"), index="user_category"
            )
            .pluck("left", {"right": {"category": True}})
            .zip()
        )
    query = (
        query.group("status")
        .count()
        .ungroup()
        .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
    )
    with app.app_context():
        status = list(query.run(db.conn))
    return status


def get_disks_ids_by_status(status=None):
    query = r.table("storage")
    if status:
        if status == "other":
            query = query.filter(
                lambda disk: r.expr(["ready", "deleted"])
                .contains(disk["status"])
                .not_()
            )
        else:
            query = query.get_all(status, index="status")

    with app.app_context():
        return list(query.pluck("id")["id"].run(db.conn))


def get_disks(user_id=None, status=None, pluck=None, category_id=None):
    query = r.table("storage")
    if user_id:
        query = query.get_all(user_id, index="user_id")
        if status:
            query = query.filter({"status": status})
    elif status:
        query = query.get_all(status, index="status")

    if pluck:
        query = query.pluck(pluck)
    else:
        query = query.pluck(
            [
                "id",
                "type",
                "status",
                "directory_path",
                "parent",
                "user_id",
                "status_logs",
                "task",
                "perms",
                {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
            ]
        )
    if category_id:
        query = (
            query.eq_join(
                [r.row["user_id"], category_id], r.table("users"), index="user_category"
            )
            .pluck("left", {"right": {"category": True}})
            .zip()
        )
    query = query.merge(
        lambda disk: {
            "user_name": r.table("users")
            .get(disk["user_id"])
            .default({"name": "[DELETED] " + disk["user_id"]})["name"],
            "category": r.table("users")
            .get(disk["user_id"])
            .default({"category": "[DELETED]"})["category"],
            "domains": r.table("domains")
            .get_all(disk["id"], index="storage_ids")
            .count(),
            "last": disk["status_logs"].default([None])[-1],
        }
    ).without("status_logs")

    with app.app_context():
        storages = list(query.run(db.conn))

    if status == "maintenance":
        for storage in storages:
            if storage.get("task"):
                storage["progress"] = Task(storage.get("task")).to_dict()["progress"]

    return storages


def get_user_ready_disks(user_id):
    query = (
        r.table("storage")
        .get_all([user_id, "ready"], index="user_status")
        .pluck(
            [
                "id",
                "user_id",
                "user_name",
                {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
                "status_logs",
            ],
        )
        .merge(
            lambda disk: {
                "user_name": r.table("users")
                .get(disk["user_id"])
                .default({"name": "[DELETED] " + disk["user_id"]})["name"],
                "category": r.table("users")
                .get(disk["user_id"])
                .default({"category": "[DELETED]"})["category"],
                "domains": r.table("domains")
                .get_all(disk["id"], index="storage_ids")
                .filter({"user": user_id})
                .pluck("id", "name")
                .coerce_to("array"),
            }
        )
    )

    with app.app_context():
        return list(query.run(db.conn))


def get_storage_domains(storage_id):
    with app.app_context():
        return list(
            r.table("domains")
            .get_all(storage_id, index="storage_ids")
            .pluck("id", "kind", "name")
            .run(db.conn)
        )


def get_media_domains(media_ids):
    with app.app_context():
        return list(
            r.table("domains")
            .get_all(media_ids, index="media_ids")
            .eq_join("user", r.table("users"))
            .pluck(
                {
                    "left": {
                        "name": True,
                        "kind": True,
                        "id": True,
                        "user": True,
                    },
                    "right": {
                        "id": True,
                        "group": True,
                        "category": True,
                        "role": True,
                        "name": True,
                        "username": True,
                    },
                }
            )
            .map(
                lambda doc: {
                    "id": doc["left"]["id"],
                    "name": doc["left"]["name"],
                    "kind": doc["left"]["kind"],
                    "user": doc["left"]["user"],
                    "user_data": {
                        "role_id": doc["right"]["role"],
                        "category_id": doc["right"]["category"],
                        "group_id": doc["right"]["group"],
                        "user_id": doc["right"]["id"],
                        "user_name": doc["right"]["name"],
                        "username": doc["right"]["username"],
                    },
                }
            )
            .merge(
                lambda doc: {
                    "category_name": r.table("categories").get(
                        doc["user_data"]["category_id"]
                    )["name"],
                    "group_name": r.table("groups").get(doc["user_data"]["group_id"])[
                        "name"
                    ],
                }
            )
            .run(db.conn)
        )


def get_storage(storage_id):
    with app.app_context():
        disk = (
            r.table("storage")
            .get(storage_id)
            .merge(
                lambda stg: {
                    "category": r.table("users").get(stg["user_id"])["category"]
                }
            )
            .run(db.conn)
        )
    return parse_disks([disk])[0]


def parse_disks(disks):
    parsed_disks = []
    for disk in disks:
        if disk.get("qemu-img-info"):
            disk["actual_size"] = disk["qemu-img-info"]["actual-size"]
            disk["virtual_size"] = disk["qemu-img-info"]["virtual-size"]
            disk["last"] = disk["status_logs"][-1]["time"]

            disk.pop("qemu-img-info")
            disk.pop("status_logs")
            parsed_disks.append(disk)
    return parsed_disks

    recursive(list(query), root)
    return root["children"]


def get_domains_delete_pending(category_id=None):
    query = r.table("storage").get_all("delete_pending", index="status")
    if category_id:
        query = query.filter({"last_domain_attached": {"category": category_id}})
    query = query.pluck(
        "id",
        "type",
        "status",
        "directory_path",
        "parent",
        "user_id",
        "status_logs",
        "last_domain_attached",
        {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
    )
    query = query.merge(
        lambda disk: {
            "user_name": r.table("users").get(disk["user_id"])["name"],
            "category_name": r.table("categories").get(
                r.table("users").get(disk["user_id"])["category"]
            )["name"],
        }
    )
    with app.app_context():
        return list(query.run(db.conn))


def get_storage_category(storage):
    with app.app_context():
        return r.table("users").get(storage.user_id).run(db.conn)["category"]


def delete_storage(storage_id):
    with app.app_context():
        if not _check(
            r.table("storage")
            .get(storage_id)
            .update({"status": "Deleting"})
            .run(db.conn),
            "replaced",
        ):
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )


def restore_disk(storage_id, restore_desktops=True):
    update = {
        "status": "ready",
        "status_logs": r.row["status_logs"].append(
            {"time": int(time.time()), "status": "ready"}
        ),
    }
    if restore_desktops:
        update["last_domain_attached"] = None
    try:
        if restore_desktops:
            with app.app_context():
                r.table("domains").insert(
                    r.table("storage").get(storage_id)["last_domain_attached"]
                ).run(db.conn)
        with app.app_context():
            r.table("storage").get(storage_id).update(update).run(db.conn)
    except:
        raise Error(
            "internal_server",
            "Internal server error",
            traceback.format_exc(),
            description_code="generic_error",
        )


def _add_storage_log(storage_id, status):
    with app.app_context():
        r.table("storage").get(storage_id).update(
            {
                "status_logs": r.row["status_logs"].append(
                    {"time": int(time.time()), "status": status}
                ),
            }
        ).run(db.conn)


def add_storage_pool(data):
    if data.get("paths"):
        _check_with_validate_weight(data["paths"])
        _check_duplicated_paths(data["paths"])
    if data.get("enabled") is False:
        data["enabled_virt"] = False
    else:
        data["enabled_virt"] = True
    remove_common_categories_from_other_pools(data["categories"])
    with app.app_context():
        r.table("storage_pool").insert(data).run(db.conn)


def get_storage_pools():
    with app.app_context():
        return list(
            r.table("storage_pool")
            .merge(
                lambda pool: {
                    "categories_names": r.branch(
                        pool["categories"].is_empty(),
                        [],
                        r.table("categories")
                        .get_all(r.args(pool["categories"]))
                        .pluck("name", "id")
                        .coerce_to("array"),
                    ),
                    "storages": r.table("hypervisors")
                    .filter(
                        lambda hyper: hyper["status"] == "Online"
                        and hyper["enabled"] == True
                        and hyper["storage_pools"].contains(pool["id"])
                    )
                    .count(),
                    "hypers": r.table("hypervisors")
                    .filter(
                        lambda hyper: hyper["status"] == "Online"
                        and hyper["enabled"] == True
                        and hyper["enabled_virt_pools"].contains(pool["id"])
                    )
                    .count(),
                    "is_default": pool["id"].eq(DEFAULT_STORAGE_POOL_ID),
                }
            )
            .run(db.conn)
        )


def get_storage_pool(storage_pool_id):
    with app.app_context():
        return r.table("storage_pool").get(storage_pool_id).run(db.conn)


def update_storage_pool(storage_pool_id, data):
    if data.get("paths"):
        _check_duplicated_paths(data["paths"])
        _check_with_validate_weight(data["paths"])
    if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
        if "enabled" in data:
            raise Error("bad_request", "Default pool can't be disabled")
        for key in ["name", "description", "mountpoint", "categories"]:
            if key in data:
                data.pop(key)
        _check_default_paths(data["paths"])

    if data.get("enabled") is False:
        data["enabled_virt"] = False
    else:
        data["enabled_virt"] = True
    remove_common_categories_from_other_pools(data["categories"])
    with app.app_context():
        r.table("storage_pool").get(storage_pool_id).update(data).run(db.conn)


def delete_storage_pool(storage_pool_id):
    if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
        raise Error("bad_request", "Default pool can't be removed")
    with app.app_context():
        r.table("storage_pool").get(storage_pool_id).delete().run(db.conn)
    with app.app_context():
        r.table("hypervisors").update(
            lambda hyper: {
                "storage_pools": hyper["storage_pools"].filter(
                    lambda pool: pool != storage_pool_id
                ),
                "enabled_storage_pools": hyper["enabled_storage_pools"].filter(
                    lambda pool: pool != storage_pool_id
                ),
                "virt_pools": hyper["virt_pools"].filter(
                    lambda pool: pool != storage_pool_id
                ),
                "enabled_virt_pools": hyper["enabled_virt_pools"].filter(
                    lambda pool: pool != storage_pool_id
                ),
            }
        ).run(db.conn)


def _check_with_validate_weight(data):
    for key in data:
        if len(data[key]):
            total = sum(item["weight"] for item in data[key])
            if total != 100:
                raise Error("bad_request", "Same type's weight sum must be 100")


def _check_duplicated_paths(data):
    seen_paths = set()
    for key in data:
        for item in data[key]:
            path = item["path"]
            if path in seen_paths:
                raise Error(
                    "bad_request", "Paths of the same pool must have a unique name"
                )
            seen_paths.add(path)


def _check_default_paths(paths):
    if not (
        any(obj.get("path") == "groups" for obj in paths["desktop"])
        and any(obj.get("path") == "media" for obj in paths["media"])
        and any(obj.get("path") == "templates" for obj in paths["template"])
        and any(obj.get("path") == "volatile" for obj in paths["volatile"])
    ):
        raise Error(
            "bad_request",
            "Default pool must have at least one empty path per type",
        )


def remove_category_from_storage_pool(category_id):
    with app.app_context():
        r.table("storage_pool").filter(
            lambda pool: pool["categories"].contains(category_id)
        ).update(
            lambda pool: pool["categories"].filter(lambda cat: cat != category_id)
        ).run(
            db.conn
        )


def get_storage_derivatives(storage_id):
    total = []
    domains = Storage(storage_id).domains
    for domain in domains:
        total.append(domain.id)
        if domain.kind == "template":
            with app.app_context():
                derivative_list = list(
                    r.table("domains")
                    .get_all(domain.id, index="parents")
                    .distinct()
                    .map(
                        lambda doc: doc.merge(
                            {
                                "storage": doc["create_dict"]["hardware"]["disks"][0][
                                    "storage_id"
                                ]
                            }
                        )
                    )
                    .pluck("id", "storage", "status")
                    .run(db.conn)
                )
            for derivative in derivative_list:
                total.append(derivative["id"])
                d = get_storage_derivatives(derivative["storage"])
                if d:
                    total.extend(d)
    return list(set(total))


def _check_domains_status(storage_id):
    for domain_id in get_storage_derivatives(storage_id):
        with app.app_context():
            domain_status = r.table("domains").get(domain_id)["status"].run(db.conn)
        if domain_status not in ["Stopped"]:
            return False
    return True


def process_check_backing_chain(storages_ids, user_id):
    try:
        for storage_id in storages_ids:
            storage = Storage(storage_id)
            storage.check_backing_chain(user_id=user_id)
        notify_admins(
            "storage_action",
            {
                "action": "check_backing_chain",
                "count": len(storages_ids),
                "status": "completed",
            },
        )
    except Error as e:
        app.logger.error(e)
        error_message = str(e)
        if isinstance(e.args, tuple) and len(e.args) > 1:
            error_message = e.args[1]
        notify_admins(
            "storage_action",
            {
                "action": "check_backing_chain",
                "count": len(storages_ids),
                "msg": error_message,
                "status": "failed",
            },
        )

    except Exception as e:
        app.logger.error(traceback.format_exc())
        notify_admins(
            "storage_action",
            {
                "action": "check_backing_chain",
                "count": len(storages_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def remove_common_categories_from_other_pools(categories):
    """
    Remove categories from other storage pools so they can be added to another pool

    :param categories: List of category ids
    :type categories: list
    """
    if len(categories):
        with app.app_context():
            existing_pools = list(
                r.table("storage_pool").pluck("categories", "id").run(db.conn)
            )
        for pool in existing_pools:
            common_categories = set(pool["categories"]).intersection(set(categories))
            if common_categories:
                with app.app_context():
                    r.table("storage_pool").get(pool["id"]).update(
                        {
                            "categories": r.row["categories"].difference(
                                list(common_categories)
                            )
                        }
                    ).run(db.conn)


def check_category_storage_pool_availability(categories_ids, storage_pool_id=None):
    """
    Check if these categories are in another storage pool

    :param categories_ids: List of category ids
    :type categories_ids: list
    :param storage_pool_id: Storage pool id
    :type storage_pool_id: str
    :return: True if none of the categories are in another storage pool, otherwise False
    :rtype: bool
    """
    query = r.table("storage_pool").pluck("categories", "id")
    if storage_pool_id:
        query = query.filter(r.row["id"] != storage_pool_id)
    existing_categories = list(query.run(db.conn))

    return not any(
        any(category_id in pool["categories"] for category_id in categories_ids)
        for pool in existing_categories
    )
