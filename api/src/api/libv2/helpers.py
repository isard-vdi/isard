#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import random
import string
import time
import traceback
import uuid
from datetime import timedelta

from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error
from ..libv2.isardViewer import isardViewer
from .flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)


isardviewer = isardViewer()


class InternalUsers(object):
    def __init__(self):
        self.users = {}

    def get(self, user_id):
        data = self.users.get(user_id, False)
        if not data:
            with app.app_context():
                try:
                    user = (
                        r.table("users")
                        .get(user_id)
                        .pluck("name", "category", "group")
                        .run(db.conn)
                    )
                    category_name = (
                        r.table("categories")
                        .get(user["category"])
                        .pluck("name")
                        .run(db.conn)["name"]
                    )
                    group_name = (
                        r.table("groups")
                        .get(user["group"])
                        .pluck("name")
                        .run(db.conn)["name"]
                    )
                    self.users[user_id] = {
                        "userName": user["name"],
                        "categoryName": category_name,
                        "groupName": group_name,
                    }
                except:
                    print(traceback.format_exc())
                    return {
                        "userName": "Unknown",
                        "userPhoto": "Unknown",
                        "categoryName": "Unknown",
                        "groupName": "Unknown",
                    }
        return self.users[user_id]

    def list(self):
        return self.users


def _get_reservables(item_type, item_id, tolist=False):
    if item_type == "desktop":
        with app.app_context():
            data = r.table("domains").get(item_id).run(db.conn)
        units = 1
        item_name = data["name"]
    elif item_type == "deployment":
        with app.app_context():
            deployment = r.table("deployments").get(item_id).run(db.conn)
        if not deployment:
            raise Error(
                "not_found",
                "Deployment id not found",
                description_code="not_found",
            )
        item_name = deployment["name"]
        with app.app_context():
            deployment_domains = list(
                r.table("domains").get_all(item_id, index="tag").run(db.conn)
            )
        if not len(deployment_domains):
            # Now there is no desktop at the deployment. No reservation will be done.
            raise (
                "precondition_required",
                "Deployment has no desktops to be reserved.",
            )
        data = deployment_domains[0]
        units = len(deployment_domains)
    else:
        raise Error(
            "not_found",
            "Item type " + str(item_type) + " not found",
            description_code="not_found",
        )

    if not data["create_dict"].get("reservables") or not any(
        list(data["create_dict"]["reservables"].values())
    ):
        raise Error(
            "precondition_required",
            "Item has no reservables",
            description_code="no_reservables",
        )
    data = data["create_dict"]["reservables"]
    data_without_falses = {k: v for k, v in data.items() if v}
    if tolist:
        return (
            [item for sublist in list(reservables.values()) for item in sublist],
            units,
        )
    return (data_without_falses, units, item_name)


def _get_domain_reservables(domain_id, toList=False):
    with app.app_context():
        data = r.table("domains").get(domain_id).run(db.conn)
    if not data["create_dict"].get("reservables") or not any(
        list(data["create_dict"]["reservables"].values())
    ):
        return {"vgpus": []}
    data = data["create_dict"]["reservables"]
    data_without_falses = {k: v for k, v in data.items() if v}
    if toList:
        return [item for sublist in list(reservables.values()) for item in sublist]
    return data_without_falses


def _parse_string(txt):
    import locale
    import re
    import unicodedata

    if type(txt) is not str:
        txt = txt.decode("utf-8")
    # locale.setlocale(locale.LC_ALL, 'ca_ES')
    prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
    if not prog.match(txt):
        raise Error(
            "internal_server",
            "Unable to parse string",
            traceback.format_exc(),
            description_code="unable_to_parse_string",
        )
    else:
        # ~ Replace accents
        txt = "".join(
            (
                c
                for c in unicodedata.normalize("NFD", txt)
                if unicodedata.category(c) != "Mn"
            )
        )
        return txt.replace(" ", "_")


def _check(dict, action):
    """
    These are the actions:
    {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
    """
    if dict[action] or dict["unchanged"]:
        return True
    if not dict["errors"]:
        return True
    return False


def _random_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$*"
    rnd = random.SystemRandom()
    return "".join(rnd.choice(chars) for i in range(length))


def _parse_media_info(create_dict):
    medias = ["isos", "floppies", "storage"]
    for m in medias:
        if m in create_dict["hardware"]:
            newlist = []
            for item in create_dict["hardware"][m]:
                with app.app_context():
                    newlist.append(
                        r.table("media")
                        .get(item["id"])
                        .pluck("id", "name", "description")
                        .run(db.conn)
                    )
            create_dict["hardware"][m] = newlist
    return create_dict


def _is_frontend_desktop_status(status):
    frontend_desktop_status = [
        "Creating",
        "CreatingAndStarting",
        "Shutting-down",
        "Stopping",
        "Stopped",
        "Starting",
        "Started",
        "Failed",
        "Downloading",
        "DownloadStarting",
    ]
    return True if status in frontend_desktop_status else False


def parse_frontend_desktop_status(desktop):
    if (
        desktop["status"].startswith("Creating")
        and desktop["status"] != "CreatingAndStarting"
    ):
        desktop["status"] = "Creating"
    return desktop


def default_guest_properties():
    return {
        "credentials": {
            "username": "isard",
            "password": "pirineus",
        },
        "fullscreen": False,
        "viewers": {
            "file_spice": {"options": None},
            "browser_vnc": {"options": None},
            "file_rdpgw": {"options": None},
            "file_rdpvpn": {"options": None},
            "browser_rdp": {"options": None},
        },
    }


def _parse_desktop(desktop):
    desktop = parse_frontend_desktop_status(desktop)
    desktop["user_name"] = r.table("users").get(desktop["user"]).run(db.conn)["name"]
    desktop["group_name"] = r.table("groups").get(desktop["group"]).run(db.conn)["name"]
    desktop["category_name"] = (
        r.table("categories").get(desktop["category"]).run(db.conn)["name"]
    )
    desktop["image"] = desktop.get("image", None)
    desktop["from_template"] = desktop.get("parents", [None])[-1]
    if desktop.get("persistent", True):
        desktop["type"] = "persistent"
    else:
        desktop["type"] = "nonpersistent"

    desktop["viewers"] = [
        v.replace("_", "-") for v in list(desktop["guest_properties"]["viewers"].keys())
    ]

    if desktop["status"] == "Started":
        if (
            "file-rdpgw" in desktop["viewers"]
            or "file-rdpvpn" in desktop["viewers"]
            or "browser-rdp" in desktop["viewers"]
        ):
            if "wireguard" in desktop["create_dict"]["hardware"]["interfaces"]:
                desktop["ip"] = desktop.get("viewer", {}).get("guest_ip")
                if not desktop["ip"]:
                    desktop["status"] = "WaitingIP"
            else:
                desktop["viewers"] = [
                    v
                    for v in desktop["viewers"]
                    if v not in ["file-rdpgw", "file-rdpvpn", "browser-rdp"]
                ]

    if desktop["status"] == "Downloading":
        progress = {
            "percentage": desktop.get("progress", {}).get("received_percent"),
            "throughput_average": desktop.get("progress", {}).get(
                "speed_download_average"
            ),
            "time_left": desktop.get("progress", {}).get("time_left"),
            "size": desktop.get("progress", {}).get("total"),
        }
    else:
        progress = None
    editable = True
    if desktop.get("tag"):
        try:
            deployment_user = (
                r.table("deployments")
                .get(desktop.get("tag"))
                .pluck("user")
                .run(db.conn)
            )["user"]
            editable = True if deployment_user == desktop["user"] else False
        except:
            log.debug(traceback.format_exc())
            editable = False
    # TODO: Sum all the desktop storages instead of getting only the first one, call get_domain_storage function to retrieve them
    desktop_size = 0
    if desktop.get("type") == "persistent" and desktop["create_dict"]["hardware"].get(
        "disks", [{}]
    )[0].get("storage_id"):
        desktop_storage = (
            r.table("storage")
            .get(desktop["create_dict"]["hardware"]["disks"][0]["storage_id"])
            .pluck({"qemu-img-info": {"actual-size"}})
            .run(db.conn)
        )
        if desktop_storage.get("qemu-img-info"):
            desktop_size = desktop_storage["qemu-img-info"]["actual-size"]
    return {
        **{
            "id": desktop["id"],
            "name": desktop["name"],
            "state": desktop["status"],
            "type": desktop["type"],
            "template": desktop["from_template"],
            "viewers": desktop["viewers"],
            "icon": desktop["icon"],
            "image": desktop["image"],
            "description": desktop["description"],
            "ip": desktop.get("ip"),
            "progress": progress,
            "editable": editable,
            "scheduled": desktop.get("scheduled", {"shutdown": False}),
            "server": desktop.get("server"),
            "accessed": desktop.get("accessed"),
            "desktop_size": desktop_size,
            "tag": desktop.get("tag"),
            "visible": desktop.get("tag_visible"),
            "user": desktop.get("user"),
            "user_name": desktop.get("user_name"),
            "group": desktop.get("group"),
            "group_name": desktop.get("group_name"),
            "category": desktop.get("category"),
            "category_name": desktop.get("category_name"),
            "reservables": desktop["create_dict"].get("reservables"),
        },
        **_parse_desktop_booking(desktop),
    }


def _parse_deployment_desktop(desktop, user_id=False):
    if desktop["status"] in ["Started", "WaitingIP"] and desktop.get("viewer", {}).get(
        "static"
    ):
        viewer = isardviewer.viewer_data(
            desktop["id"],
            "browser-vnc",
            get_cookie=False,
            get_dict=True,
            domain=desktop,
            user_id=user_id,
        )
    else:
        viewer = False
    user_photo = desktop.get("user_photo")
    desktop = _parse_desktop(desktop)
    desktop["viewer"] = viewer
    desktop["user_photo"] = user_photo

    return desktop


def _parse_desktop_booking(desktop):
    if not desktop["create_dict"].get("reservables") or not any(
        list(desktop["create_dict"]["reservables"].values())
    ):
        return {
            "needs_booking": False,
            "next_booking_start": None,
            "next_booking_end": None,
            "booking_id": False,
        }
    item_id = desktop["id"]
    item_type = "desktop"
    with app.app_context():
        booking = (
            r.table("bookings")
            .get_all([item_type, item_id], index="item_type-id")
            .filter(lambda b: b["end"] > r.now())
            .order_by("start")
            .run(db.conn)
        )
        if not booking and desktop.get("tag"):
            booking = (
                r.table("bookings")
                .get_all(["deployment", desktop.get("tag")], index="item_type-id")
                .filter(lambda b: b["end"] > r.now())
                .order_by("start")
                .run(db.conn)
            )

    if booking:
        return {
            "needs_booking": True,
            "next_booking_start": booking[0]["start"].strftime("%Y-%m-%dT%H:%M%z"),
            "next_booking_end": booking[0]["end"].strftime("%Y-%m-%dT%H:%M%z"),
            "booking_id": desktop.get("booking_id", False),
        }
    else:
        return {
            "needs_booking": True,
            "next_booking_start": None,
            "next_booking_end": None,
            "booking_id": False,
        }


def _parse_deployment_booking(deployment):
    with app.app_context():
        deployment_domains = list(
            r.table("domains").get_all(deployment["id"], index="tag").run(db.conn)
        )
    if not len(deployment_domains):
        return {
            "needs_booking": False,
            "next_booking_start": None,
            "next_booking_end": None,
            "booking_id": False,
        }
    desktop = deployment_domains[0]
    return _parse_desktop_booking(desktop)


def parse_domain_insert(new_data):
    if new_data.get("hardware", {}).get("reservables", {}).get("vgpus") == ["None"]:
        new_data["hardware"]["reservables"]["vgpus"] = None

    return new_data


def parse_domain_update(domain_id, new_data, admin_or_manager=False):
    with app.app_context():
        domain = r.table("domains").get(domain_id).run(db.conn)
    if not domain:
        raise Error(
            "not_found",
            "Not found domain to be updated",
            traceback.format_exc(),
            description="not_found",
        )
    new_domain = {}

    if admin_or_manager:
        if "forced_hyp" in new_data and new_data.get("forced_hyp") != domain.get(
            "forced_hyp"
        ):
            new_domain["forced_hyp"] = new_data.get("forced_hyp")
        if "favourite_hyp" in new_data and new_data.get("favourite_hyp") != domain.get(
            "favourite_hyp"
        ):
            new_domain["favourite_hyp"] = new_data.get("favourite_hyp")
        if "server" in new_data and new_data.get("server") != domain.get("server"):
            new_domain = {
                **new_domain,
                **{
                    "server": new_data.get("server"),
                },
            }
        if "xml" in new_data and new_data.get("xml") != domain.get("xml"):
            new_domain = {
                **new_domain,
                **{"status": "Updating", "xml": new_data["xml"]},
            }

    if "name" in new_data and new_data.get("name") != domain.get("name"):
        new_domain["name"] = new_data.get("name")
    if "description" in new_data and new_data.get("description") != domain.get(
        "description"
    ):
        new_domain["description"] = new_data.get("description")

    if new_data.get("guest_properties") and new_data.get(
        "guest_properties"
    ) != domain.get("guest_properties"):
        new_domain["guest_properties"] = {
            **new_data["guest_properties"],
            **{"viewers": r.literal(new_data["guest_properties"].pop("viewers"))},
        }

    if new_data.get("hardware") and new_data.get("hardware") != domain.get("hardware"):
        if new_data["hardware"].get("virtualization_nested"):
            new_data["hardware"]["virtualization_nested"] = new_data["hardware"][
                "virtualization_nested"
            ]
        if new_data["hardware"].get("memory"):
            new_data["hardware"]["memory"] = int(
                new_data["hardware"]["memory"] * 1048576
            )
        if new_data["hardware"].get("disk_bus"):
            disk_bus = (
                new_data["hardware"]["disk_bus"]
                if new_data["hardware"]["disk_bus"] != "default"
                else "virtio"
            )
            new_data["hardware"] = {
                **new_data["hardware"],
                **{
                    "disks": [
                        {
                            **domain["create_dict"]["hardware"]["disks"][0],
                            **{"bus": disk_bus},
                        }
                    ]
                },
            }
        if new_data["hardware"].get("reservables"):
            if new_data["hardware"]["reservables"].get("vgpus") == ["None"]:
                new_data["hardware"]["reservables"]["vgpus"] = None
            new_domain = {
                **new_domain,
                **{
                    "status": "Updating",
                    "create_dict": {
                        "hardware": new_data["hardware"],
                        "reservables": r.literal(
                            new_data["hardware"].pop("reservables")
                        ),
                    },
                },
            }
        else:
            new_domain = {
                **new_domain,
                **{
                    "status": "Updating",
                    "create_dict": {"hardware": new_data["hardware"]},
                },
            }
    return new_domain


def generate_db_media(path_downloaded, filesize):
    media_id = str(uuid.uuid4())
    admin_data = get_user_data()

    icon = False
    if path_downloaded.split(".")[-1] == "iso":
        icon = "fa-circle-o"
        kind = "iso"
    if path_downloaded.split(".")[-1] == "fd":
        icon = "fa-floppy-o"
        kind = "floppy"
    if path_downloaded.split(".")[-1].startswith("qcow"):
        icon = "fa-hdd-o"
        kind = path_downloaded.split(".")[-1]
    if not icon:
        raise Error(
            "precondition_required",
            "Skipping uploaded file as has unknown extension",
            traceback.format_exc(),
            description_code="unknown_extension",
        )

    with app.app_context():
        username = r.table("users").get(parts[-2])["username"].run(db.conn)
    if username == None:
        raise Error(
            "not_found",
            "Username not found",
            traceback.format_exc(),
            description_code="not_found",
        )

    return {
        "accessed": int(time.time()),
        "allowed": {
            "categories": False,
            "groups": False,
            "roles": False,
            "users": False,
        },
        "category": admin_data["category"],
        "description": "Scanned from storage.",
        "detail": "",
        "group": admin_data["group"],
        "hypervisors_pools": ["default"],
        "icon": icon,
        "id": media_id,
        "kind": kind,
        "name": path_downloaded.split("/")[-1],
        "path": "/".join(
            path_downloaded.rsplit("/", 6)[2:]
        ),  # "default/default/local/admin-admin/dsl-4.4.10.iso" ,
        "path_downloaded": path_downloaded,
        "progress": {
            "received": filesize,
            "received_percent": 100,
            "speed_current": "10M",
            "speed_download_average": "10M",
            "speed_upload_average": "0",
            "time_left": "--:--:--",
            "time_spent": "0:00:05",
            "time_total": "0:00:05",
            "total": filesize,
            "total_percent": 100,
            "xferd": "0",
            "xferd_percent": "0",
        },
        "status": "Downloaded",
        "url-isard": False,
        "url-web": False,
        "user": admin_data["user"],  # "local-default-admin-admin" ,
        "username": admin_data["username"],
    }


def get_user_data(user_id="admin"):
    if user_id == "admin":
        with app.app_context():
            user = list(
                r.table("users")
                .get_all("admin", index="uid")
                .filter({"provider": "local"})
                .run(db.conn)
            )[0]
    else:
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
    return {
        "category": user["category"],
        "group": user["group"],
        "user": user["id"],
        "username": user["username"],
    }


def gen_payload_from_user(user_id):
    with app.app_context():
        user = (
            r.table("users")
            .get(user_id)
            .merge(
                lambda d: {
                    "category_name": r.table("categories").get(d["category"])["name"],
                    "group_name": r.table("groups").get(d["group"])["name"],
                    "role_name": r.table("roles").get(d["role"])["name"],
                }
            )
            .without("password")
            .run(db.conn)
        )
    return {
        "provider": user["provider"],
        "user_id": user["id"],
        "name": user["name"],
        "uid": user["uid"],
        "username": user["username"],
        "photo": user.get("photo", ""),
        "role_id": user["role"],
        "role_name": user["role_name"],
        "category_id": user["category"],
        "category_name": user["category_name"],
        "group_id": user["group"],
        "group_name": user["group_name"],
    }
