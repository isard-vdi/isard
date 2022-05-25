#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import pprint
import time
import traceback
from datetime import datetime, timedelta

from mergedeep import merge
from rethinkdb import RethinkDB

from api import app

from .api_exceptions import Error

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from ..libv2.api_cards import ApiCards

api_cards = ApiCards()


from .ds import DS

ds = DS()

from .helpers import _check, _disk_path, _parse_media_info, _parse_string


class ApiDesktopsPersistent:
    def __init__(self):
        None

    def Delete(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if desktop == None:
            raise Error("not_found", "Desktop not found", traceback.format_stack())
        ds.delete_desktop(desktop_id, desktop["status"])

    def NewFromTemplate(
        self,
        desktop_name,
        desktop_description,
        template_id,
        payload,
        deployment=False,
        forced_hyp=False,
    ):
        with app.app_context():
            template = r.table("domains").get(template_id).run(db.conn)
        if template == None:
            raise Error("not_found", "Template not found", traceback.format_stack())

        parsed_name = _parse_string(desktop_name)

        parent_disk = template["hardware"]["disks"][0]["file"]
        dir_disk = "/".join(
            (
                payload["category_id"],
                payload["group_id"].replace(f"{payload['category_id']}-", ""),
                payload["user_id"].split("-", 1)[0],
                "-".join(payload["user_id"].rsplit("-", 2)[-2:]),
            )
        )
        disk_filename = parsed_name + ".qcow2"

        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"file": dir_disk + "/" + disk_filename, "parent": parent_disk}
        ]
        create_dict = _parse_media_info(create_dict)

        if "interfaces_mac" in create_dict["hardware"].keys():
            create_dict["hardware"].pop("interfaces_mac")

        new_desktop = {
            "id": "_" + payload["user_id"] + "-" + parsed_name,
            "name": desktop_name,
            "description": desktop_description,
            "kind": "desktop",
            "user": payload["user_id"],
            "username": payload["user_id"].split("-")[-1],
            "status": "Creating",
            "detail": None,
            "category": payload["category_id"],
            "group": payload["group_id"],
            "xml": None,
            "icon": template["icon"],
            "image": template["image"],
            "server": template["server"],
            "os": template["os"],
            "options": {"viewers": {"spice": {"fullscreen": True}}},
            "create_dict": {
                "hardware": create_dict["hardware"],
                "origin": template["id"],
            },
            "hypervisors_pools": template["hypervisors_pools"],
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "accessed": time.time(),
            "persistent": True,
            "forced_hyp": forced_hyp,
            "from_template": template["id"],
        }
        if deployment:
            new_desktop = {**new_desktop, **deployment}

        with app.app_context():
            if r.table("domains").get(new_desktop["id"]).run(db.conn) == None:
                if (
                    _check(
                        r.table("domains").insert(new_desktop).run(db.conn), "inserted"
                    )
                    == False
                ):
                    raise NewDesktopNotInserted
                else:
                    return new_desktop["id"]
            else:
                raise DesktopExists

    def NewFromScratch(
        self,
        name,
        user_id,
        description="Created from api v3",
        disk_user=False,
        disk_path=False,
        disk_path_selected="/isard/groups",
        disk_bus="virtio",
        disk_size=False,
        disks=False,
        isos=[],  # ['_local-default-admin-admin-systemrescue-8.04-amd64.iso']
        boot_order=["disk"],
        vcpus=2,
        memory=4096,
        graphics=["default"],
        videos=["default"],
        interfaces=["default"],
        opsystem="windows",
        icon="circle-o",
        image="",
        forced_hyp=False,
        hypervisors_pools=["default"],
        server=False,
        virt_install_id=False,
        xml=None,
    ):
        ## If disk_path is False then generates path from user_id
        ## If disks is not False then should be a list
        ## Isos [']
        ## takes virt_install_id if xml is None else puts the xml

        ## TODO: quotas??

        # Default status:
        json_status = {"status": "CreatingDomainFromDisk"}

        # Get user_id
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if user == None:
            raise Error("not_found", "User not found", traceback.format_stack())

        json_user = {
            "user": user["id"],
            "username": user["username"],
            "category": user["category"],
            "group": user["group"],
        }

        json_allowed = {
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            }
        }

        # Parse desktop name
        desktop_name_parsed = _parse_string(name)
        desktop_id = "_" + user["id"] + "-" + desktop_name_parsed

        with app.app_context():
            if r.table("domains").get(desktop_id).run(db.conn) != None:
                raise DesktopExists

        # Get xml (from virt_install or xml)
        if xml is None:
            with app.app_context():
                vi = r.table("virt_install").get(virt_install_id).run(db.conn)
            if vi == None:
                raise Error(
                    "not_found", "Virt install id not found", traceback.format_stack()
                )
            domain["create_dict"]["create_from_virt_install_xml"] = virt_install_id
            json_xml = {
                "create_dict": {"create_from_virt_install_xml": virt_install_id},
                "xml": vi["xml"],
            }
        else:
            json_xml = {"xml": xml}

        # OPTIONS

        # Get disk(s) dict
        if disks:
            try:
                for disk in disks:
                    if not disk.get("file"):
                        raise DisksFileError
                    if not disk.get("path_selected"):
                        raise DisksPathselectedError
            except:
                raise DisksFormatError
        elif disk_path:
            disks = [
                {
                    "file": disk_path,
                    "path_selected": disk_path_selected,
                    "size": disk_size,
                }
            ]
        elif disk_user:
            dir_disk, disk_filename = _disk_path(user, desktop_name_parsed)
            disks = [
                {
                    "file": dir_disk + "/" + disk_filename,
                    "path_selected": disk_path_selected,
                    "size": disk_size,
                }
            ]
        else:
            disks = []

        json_disks = {
            "create_dict": {"hardware": {"disks": disks}},
            "hardware": {"hardware": {"disks": disks}},
        }

        # Get iso(s) list of dicts (we should put it in media??)
        list_isos = []
        for iso in isos:
            with app.app_context():
                dbiso = r.table("media").get(iso).run(db.conn)
            if dbiso == None:
                raise Error("not_found", "Media not found", traceback.format_stack())
            list_isos.append({"id": iso})
        json_isos = {"create_dict": {"hardware": {"isos": list_isos}}}

        # Check that graphics,videos,interfaces exists!
        list_graphics = []
        for graphic in graphics:
            with app.app_context():
                dbgraphic = r.table("graphics").get(graphic).run(db.conn)
            if dbgraphic == None:
                raise Error("not_found", "Graphic not found", traceback.format_stack())
            list_graphics.append(graphic)
        json_graphics = {"create_dict": {"hardware": {"graphics": list_graphics}}}

        list_videos = []
        for video in videos:
            with app.app_context():
                dbvideo = r.table("videos").get(video).run(db.conn)
            if dbvideo == None:
                raise Error("not_found", "Video not found", traceback.format_stack())
            list_videos.append(video)
        json_videos = {"create_dict": {"hardware": {"videos": list_videos}}}

        list_interfaces = []
        for interface in interfaces:
            with app.app_context():
                dbinterface = r.table("interfaces").get(interface).run(db.conn)
            if dbinterface == None:
                raise Error(
                    "not_found", "Interface not found", traceback.format_stack()
                )
            list_interfaces.append(interface)
        json_interfaces = {"create_dict": {"hardware": {"interfaces": list_interfaces}}}

        # We don't check the forced hyp as now can't be in db if down

        domain = {
            "id": desktop_id,
            "kind": "desktop",
            "name": name,
            "description": description,
            "icon": icon,
            "image": image,
            "detail": "Creating desktop from existing disk and checking if it is valid (can start)",
            "os": opsystem,
            "server": server,
            "create_dict": {
                "forced_hyp": forced_hyp,
                "hardware": {
                    "boot_order": boot_order,
                    "diskbus": disk_bus,
                    "floppies": [],
                    "memory": memory,
                    "vcpus": vcpus,
                    "videos": videos,
                },
            },
            "hyp_started": "",
            "hypervisors_pools": hypervisors_pools,
            "options": {"viewers": {"spice": {"fullscreen": False}}},
        }

        result = merge(
            domain,
            json_user,
            json_allowed,
            json_xml,
            json_disks,
            json_isos,
            json_graphics,
            json_videos,
            json_interfaces,
            json_status,
        )
        with app.app_context():
            r.table("domains").insert(result).run(db.conn)
        return result["id"]

    def UserDesktop(self, desktop_id):
        try:
            with app.app_context():
                return (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("user")
                    .run(db.conn)["user"]
                )
        except:
            raise Error("not_found", "Desktop not found", traceback.format_stack())

    def Start(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if desktop["status"] == "Started":
                return desktop_id
            if desktop["status"] not in ["Stopped", "Failed"]:
                raise DesktopActionFailed
        if desktop == None:
            raise Error("not_found", "Desktop not found", traceback.format_stack())
        # Start the domain
        ds.WaitStatus(desktop_id, "Any", "Starting", "Started")
        return desktop_id

    def Stop(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if desktop["status"] == "Stopped":
                return desktop_id
            if desktop["status"] != "Started":
                raise DesktopActionFailed
        if desktop == None:
            raise Error("not_found", "Desktop not found", traceback.format_stack())
        # Stop the domain
        try:
            # ds.WaitStatus(desktop_id, 'Any', 'Shutting-down', 'Stopped', wait_seconds=30)
            ds.WaitStatus(desktop_id, "Any", "Stopping", "Stopped", wait_seconds=10)
        except:
            ds.WaitStatus(desktop_id, "Any", "Stopping", "Stopped")
        return desktop_id

    def Update(self, desktop_id, desktop_data):
        with app.app_context():
            return _check(
                r.table("domains").get(desktop_id).update(desktop_data).run(db.conn),
                "replaced",
            )
