#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import time
from datetime import datetime, timedelta

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


import random
import string

import bcrypt

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

import traceback

from .api_exceptions import Error


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
            "internal_server", "Unable to parse string", traceback.format_stack()
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


def _disk_path(user, parsed_name):
    with app.app_context():
        group_uid = r.table("groups").get(user["group"]).run(db.conn)["uid"]

    dir_path = (
        user["category"]
        + "/"
        + group_uid
        + "/"
        + user["provider"]
        + "/"
        + user["uid"]
        + "-"
        + user["username"]
    )
    filename = parsed_name + ".qcow2"
    return dir_path, filename


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


def _parse_desktop(desktop):
    desktop = parse_frontend_desktop_status(desktop)
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
                desktop["viewers"].extend(["file-rdpgw", "file-rdpvpn", "browser-rdp"])

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
    return {
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
    }


def _parse_deployment_desktop(desktop, user_id=False):
    visible = desktop.get("tag_visible", False)
    user = desktop["user"]
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
    desktop = _parse_desktop(desktop)
    desktop["viewer"] = viewer
    desktop = {**desktop, **app.internal_users.get(user), **{"visible": visible}}
    desktop["user"] = user
    desktop.pop("type")
    desktop.pop("template")

    return desktop


# suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
# def humansize(nbytes):
#     i = 0
#     while nbytes >= 1024 and i < len(suffixes)-1:
#         nbytes /= 1024.
#         i += 1
#     f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
#     return '%s %s' % (f, suffixes[i])


def generate_db_media(path_downloaded, filesize):
    parts = path_downloaded.split("/")
    # /isard/media/default/default/local/admin-admin/dsl-4.4.10.iso
    media_id = "_" + parts[-3] + "-" + parts[-5] + "-" + parts[-2] + "-" + parts[-1]
    group_id = parts[-5] + "-" + parts[-4]

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
            traceback.format_stack(),
        )
    return {
        "accessed": time.time(),
        "allowed": {
            "categories": False,
            "groups": False,
            "roles": False,
            "users": False,
        },
        "category": parts[-5],
        "description": "Scanned from storage.",
        "detail": "",
        "group": group_id,
        "hypervisors_pools": ["default"],
        "icon": icon,
        "id": media_id,
        "kind": kind,
        "name": parts[-1],
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
        "user": parts[-3]
        + "-"
        + parts[-5]
        + "-"
        + parts[-2],  # "local-default-admin-admin" ,
        "username": parts[-2].split("-")[1],
    }
