#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from isardvdi_common.media import Media
from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.task import Task
from rethinkdb import RethinkDB

from api import app

from ..libv2.api_desktop_events import desktop_stop, desktop_updating

r = RethinkDB()
import traceback

from ..libv2.api_cards import ApiCards

api_cards = ApiCards()

from isardvdi_common.api_exceptions import Error

from ..libv2.api_desktops_persistent import (
    ApiDesktopsPersistent,
    unassign_resource_from_desktops_and_deployments,
)
from .api_allowed import ApiAllowed
from .flask_rethink import RDB
from .helpers import _check

db = RDB(app)
db.init_app(app)
api_allowed = ApiAllowed()

persistent = ApiDesktopsPersistent()


def media_task_delete(media_id, user_id=None, keep_status=None):
    media = Media(media_id)

    if not Media.exists(media_id):
        raise Error(error="not_found", description="Media not found")

    if media.status not in [
        "Downloaded",
        "DownloadFailed",
        "DownloadFailedInvalidFormat",
    ]:
        raise Error(
            error="precondition_required",
            description="Media not ready to be deleted",
            description_code="media_should_not_be_downloading",
        )

    actual_status = media.status
    if media.status == "DownloadFailedInvalidFormat" and not keep_status:
        r.table("media").get(media.id).update({"status": "deleted"}).run(db.conn)
        return
    finished_status = actual_status if keep_status else "deleted"
    if actual_status == "DownloadFailed":
        media.status = "deleted"
        return
    else:
        media.status = "maintenance"
    task_id = Task(
        user_id=user_id,
        queue=f"storage.{StoragePool.get_best_for_action('delete', path=media.path_downloaded.rsplit('/', 1)[0]).id}.default",
        task="delete",
        job_kwargs={
            "kwargs": {
                "path": media.path_downloaded,
            },
        },
        dependents=[
            {
                "queue": "core",
                "task": "update_status",
                "job_kwargs": {
                    "kwargs": {
                        "statuses": {
                            "finished": {
                                "deleted": {
                                    "media": [media.id],
                                },
                            },
                            "failed": {
                                "Downloaded": {"media": [media.id]},
                            },
                            "canceled": {
                                "Downloaded": {
                                    "media": [media.id],
                                },
                            },
                        },
                    },
                },
            }
        ],
    ).id
    return task_id


class ApiMedia:
    def __init__(self):
        None

    def List(self, domain_id):
        with app.app_context():
            domain_cd = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "hardware"})
                .run(db.conn)["create_dict"]["hardware"]
            )
        media = []
        if "isos" in domain_cd and domain_cd["isos"] != []:
            for m in domain_cd["isos"]:
                try:
                    iso = (
                        r.table("media")
                        .get(m["id"])
                        .pluck("id", "name", {"progress": "total"})
                        .merge({"kind": "iso"})
                        .run(db.conn)
                    )
                    iso["size"] = iso.pop("progress")["total"]
                    media.append(iso)
                except:
                    """Media does not exist"""
                    None
        if "floppies" in domain_cd and domain_cd["floppies"] != []:
            for m in domain_cd["floppies"]:
                try:
                    fd = (
                        r.table("media")
                        .get(m["id"])
                        .pluck("id", "name", {"progress": "total"})
                        .merge({"kind": "fd"})
                        .run(db.conn)
                    )
                    fd["size"] = fd.pop("progress")["total"]
                    media.append(fd)
                except:
                    """Media does not exist"""
                    None
        return media

    def Media(self, payload):
        with app.app_context():
            media = list(
                r.table("media").get_all(payload["user_id"], index="user").run(db.conn)
            )
        return [{**m, "editable": True} for m in media]

    def Get(self, media_id):
        with app.app_context():
            media = r.table("media").get(media_id).run(db.conn)
        if not media:
            raise Error(
                "not_found",
                "Not found media: " + media_id,
                traceback.format_exc(),
                description_code="not_found",
            )
        return media

    def DesktopList(self, media_id):
        with app.app_context():
            desktops = list(
                r.table("domains")
                .filter(
                    lambda dom: dom["create_dict"]["hardware"]["isos"].contains(
                        lambda media: media["id"].eq(media_id)
                    )
                )
                .merge(lambda d: {"user_name": r.table("users").get(d["user"])["name"]})
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "status",
                    "user",
                    "user_name",
                    {"create_dict": {"hardware": {"isos"}}},
                )
                .run(db.conn)
            )
        return desktops

    def DeleteDesktops(self, media_id):
        for desktop in self.DesktopList(media_id):
            if desktop["status"] in ["Starting", "Started", "Shutting-down"]:
                try:
                    desktop_stop(desktop["id"], force=True, wait_seconds=30)
                except:
                    pass

        unassign_resource_from_desktops_and_deployments("media", {"id": media_id})
        for desktop in self.DesktopList(media_id):
            desktop_updating(desktop["id"])

    def count(self, user_id):
        return r.table("media").get_all(user_id, index="user").count().run(db.conn)


def domain_from_disk(user, name, description, icon, create_dict, hyper_pools):
    with app.app_context():
        userObj = (
            r.table("users")
            .get(user)
            .pluck("id", "category", "group", "provider", "username", "uid")
            .run(db.conn)
        )

    parsed_name = name
    media_id = create_dict.pop("media")
    media = r.table("media").get(media_id).run(db.conn)
    create_dict["hardware"]["disks"] = [
        {"file": media["path"], "size": media["progress"]["total"]}
    ]  # 15G as a format
    image = api_cards.generate_default_card("_" + user + "-" + parsed_name, name)
    new_domain = {
        "id": "_" + user + "-" + parsed_name,
        "name": name,
        "description": description,
        "kind": "desktop",
        "user": userObj["id"],
        "username": userObj["username"],
        "status": "CreatingDiskFromScratch",
        "detail": None,
        "category": userObj["category"],
        "group": userObj["group"],
        "xml": None,
        "icon": icon,
        "image": image
        if image
        else {
            "id": "_" + user + "-" + parsed_name,
            "url": "/assets/img/desktops/stock/1.jpg",
            "type": "stock",
        },
        "server": False,
        "os": create_dict["create_from_virt_install_xml"],  #### Or name
        "options": {"viewers": {"spice": {"fullscreen": False}}},
        "create_dict": create_dict,
        "hypervisors_pools": hyper_pools,
        "allowed": {
            "roles": False,
            "categories": False,
            "groups": False,
            "users": False,
        },
    }
    with app.app_context():
        if _check(r.table("domains").insert(new_domain).run(db.conn), "inserted"):
            return _check(
                r.table("media").get(media_id).delete().run(db.conn), "deleted"
            )
    return False


def parseHardwareFromIso(create_dict, payload):
    create_dict["hardware"]["virtualization_nested"] = False
    if "boot_order" not in create_dict["hardware"].keys():
        try:
            create_dict["hardware"]["boot_order"] = [
                api_allowed.get_items_allowed(payload, "boots", query_pluck=["id"])[0][
                    "id"
                ]
            ]
        except:
            create_dict["hardware"]["boot_order"] = ["iso"]
    else:
        create_dict["hardware"]["boot_order"] = [create_dict["hardware"]["boot_order"]]

    if "interfaces" not in create_dict["hardware"].keys():
        try:
            create_dict["hardware"]["interfaces"] = [
                api_allowed.get_items_allowed(
                    payload, "interfaces", query_pluck=["id"]
                )[0]["id"]
            ]
        except:
            create_dict["hardware"]["interfaces"] = ["default"]
    else:
        create_dict["hardware"]["interfaces"] = [create_dict["hardware"]["interfaces"]]

    if "graphics" not in create_dict["hardware"].keys():
        try:
            create_dict["hardware"]["graphics"] = [
                api_allowed.get_items_allowed(payload, "graphics", query_pluck=["id"])[
                    0
                ]["id"]
            ]
        except:
            create_dict["hardware"]["graphics"] = ["default"]
    else:
        create_dict["hardware"]["graphics"] = [create_dict["hardware"]["graphics"]]

    if "videos" not in create_dict["hardware"].keys():
        try:
            create_dict["hardware"]["videos"] = [
                api_allowed.get_items_allowed(payload, "videos", query_pluck=["id"])[0][
                    "id"
                ]
            ]
        except:
            create_dict["hardware"]["videos"] = ["default"]
    else:
        create_dict["hardware"]["videos"] = [create_dict["hardware"]["videos"]]

    if "hypervisors_pools" not in create_dict.keys():
        try:
            create_dict["hypervisors_pools"] = [
                api_allowed.get_items_allowed(
                    payload, "hypervisors_pools", query_pluck=["id"]
                )[0]["id"]
            ]
        except:
            create_dict["hypervisors_pools"] = ["default"]
    else:
        create_dict["hypervisors_pools"] = [create_dict["hypervisors_pools"]]

    if "forced_hyp" not in create_dict.keys():
        create_dict["forced_hyp"] = False
    else:
        None  # use passed forced_hyp from form

    if "favourite_hyp" not in create_dict.keys():
        create_dict["favourite_hyp"] = False
    else:
        None

    if "memory" not in create_dict["hardware"].keys():
        create_dict["hardware"]["memory"] = int(1.5 * 1048576)
    else:
        create_dict["hardware"]["memory"] = int(
            float(create_dict["hardware"]["memory"]) * 1048576
        )

    if "vcpus" not in create_dict["hardware"].keys():
        create_dict["hardware"]["vcpus"] = 1
    else:
        create_dict["hardware"]["vcpus"] = int(create_dict["hardware"]["vcpus"])

    for disk in create_dict["hardware"]["disks"]:
        if not disk.get("bus"):
            try:
                disk["bus"] = [
                    api_allowed.get_items_allowed(
                        payload, "disk_bus", query_pluck=["id"]
                    )[0]["id"]
                ]
            except:
                disk["bus"] = ["virtio"]
        else:
            disk["bus"] = [disk["bus"]]

    return create_dict
