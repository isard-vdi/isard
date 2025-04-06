#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import copy
import json
import logging as log
import secrets
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

import gevent
import pytz

from api import socketio

from ..libv2.api_desktops_common import ApiDesktopsCommon
from ..libv2.api_logging import logs_domain_event_directviewer
from ..libv2.api_templates import ApiTemplates
from ..libv2.quotas import Quotas
from ..libv2.recycle_bin import delete_dependants_recycle_bin_from_templates

templates = ApiTemplates()
quotas = Quotas()

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from isardvdi_common.domain import Domain
from rethinkdb import RethinkDB

from api import app

from ..libv2.bookings.api_reservables_planner_compute import payload_priority
from ..libv2.validators import _validate_item, check_user_duplicated_domain_name
from .api_desktop_events import desktop_start, desktop_updating

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_cards import ApiCards, get_domain_stock_card
from ..libv2.bookings.api_booking import Bookings

apib = Bookings()
api_cards = ApiCards()
common = ApiDesktopsCommon()
from ..libv2.api_storage import get_media_domains, get_storage_derivatives
from ..libv2.bookings.api_reservables import Reservables

api_ri = Reservables()
api_allowed = ApiAllowed()

from ..views.decorators import ownsDomainId
from .api_desktop_events import (
    desktop_delete,
    desktop_reset,
    desktop_stop,
    desktops_delete,
)
from .caches import get_document
from .helpers import (
    _check,
    _get_reservables,
    _parse_media_info,
    default_guest_properties,
    gen_new_mac,
    gen_payload_from_user,
    parse_domain_insert,
    parse_domain_update,
    set_current_booking,
)
from .rules import get_unused_item_timeout

MIN_AUTOBOOKING_TIME = 30
MAX_BOOKING_TIME = 12 * 60  # 12h


def api_jumperurl_gencode(length=32):
    code = False
    while code == False:
        code = secrets.token_urlsafe(length)
        with app.app_context():
            found = list(
                r.table("domains").get_all(code, index="jumperurl").run(db.conn)
            )
        if len(found) == 0:
            return code
    raise Error(
        "internal_server",
        "Unable to create jumperurl code",
        traceback.format_exc(),
        description_code="generic_error",
    )


class ApiDesktopsPersistent:
    def __init__(self):
        None

    def Delete(self, desktop_id, agent_id, permanent):
        get_document("domains", desktop_id)
        desktop_delete(desktop_id, agent_id, permanent)

    def Get(self, desktop_id):
        return get_document("domains", desktop_id)

    def new_from_templateTh(self, desktops, deployment):
        def process_desktops():
            socketio.emit(
                "creating_desktops",
                json.dumps({"deployment_id": deployment["id"]}),
                namespace="/userspace",
                room=[deployment["user"]] + deployment["co_owners"],
            )
            for desktop in desktops:
                result = self.new_from_template(
                    desktop["name"],
                    desktop["description"],
                    desktop["template_id"],
                    desktop["user_id"],
                    desktop["domain_id"],
                    desktop["deployment_tag_dict"],
                    desktop["new_data"],
                    desktop["image"],
                )
                if result is not None:
                    set_current_booking(
                        {
                            "id": result["id"],
                            "tag": result["tag"],
                            "create_dict": result["create_dict"],
                        }
                    )
                time.sleep(0.25)
            socketio.emit(
                "end_creating_desktops",
                json.dumps({"deployment_id": deployment["id"]}),
                namespace="/userspace",
                room=[deployment["user"]] + deployment["co_owners"],
            )

        # Spawn the process_desktops greenlet and return immediately
        gevent.spawn(process_desktops)

    def new_from_template(
        self,
        desktop_name,
        desktop_description,
        template_id,
        user_id,
        domain_id=str(uuid.uuid4()),
        deployment_tag_dict=False,
        new_data=None,
        image=None,
        insert=True,
    ):
        template = get_document("domains", template_id)
        if not template:
            raise Error(
                "not_found",
                "Template not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        user = get_document("users", user_id, ["id", "username", "category", "group"])
        if user is None:
            raise Error(
                "not_found",
                f"new_from_template: user id {user_id} not found.",
                description_code="not_found",
            )

        if new_data:
            # In new data interfaces are a list of ids
            if not new_data.get("hardware", {}).get("interfaces"):
                new_data["hardware"]["interfaces"] = template["create_dict"][
                    "hardware"
                ]["interfaces"]
            template["create_dict"]["hardware"] = {
                **template["create_dict"]["hardware"],
                **parse_domain_insert(new_data)["hardware"],
            }
            if new_data["hardware"].get("reservables"):
                template["create_dict"]["reservables"] = new_data["hardware"][
                    "reservables"
                ]
                template["create_dict"]["hardware"].pop("reservables")
            else:
                template["create_dict"]["reservables"] = {"vgpus": None}
        else:
            # In template interfaces are a list of dicts (as we inherited from existing template)
            # so we need to convert them to a list of ids
            template["create_dict"]["hardware"]["interfaces"] = [
                i["id"] for i in template["create_dict"]["hardware"]["interfaces"]
            ]
            # Generate new macs always for new desktops
            template["create_dict"]["hardware"] = {
                **template["create_dict"]["hardware"],
                **parse_domain_insert(template["create_dict"])["hardware"],
            }
        parent_disk = template["hardware"]["disks"][0]["file"]
        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]
        try:
            create_dict = _parse_media_info(create_dict)
        except:
            raise Error(
                "internal_server",
                "new_from_template: unable to parse media info.",
                description_code="unable_to_parse_media",
            )

        if not deployment_tag_dict:
            payload = gen_payload_from_user(user_id)
            create_dict = quotas.limit_user_hardware_allowed(payload, create_dict)
        new_desktop = {
            "id": domain_id,
            "name": desktop_name,
            "description": desktop_description,
            "kind": "desktop",
            "user": user_id,
            "username": user["username"],
            "status": "Creating",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": None,
            "icon": template["icon"],
            "image": template["image"],
            "server": False,
            "os": template["os"],
            "guest_properties": (
                new_data.get("guest_properties")
                if new_data and new_data.get("guest_properties")
                else template["guest_properties"]
            ),
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
            "accessed": int(time.time()),
            "persistent": True,
            "forced_hyp": template.get("forced_hyp", False),
            "favourite_hyp": template.get("favourite_hyp", False),
            "from_template": template["id"],
            "tag": False,
            "tag_name": False,
            "tag_visible": False,
            "booking_id": False,
        }
        if deployment_tag_dict:
            new_desktop = {**new_desktop, **deployment_tag_dict}

        new_desktop["create_dict"]["hardware"]["memory"] = (
            int(new_data["hardware"]["memory"] * 1048576)
            if new_data and new_data.get("hardware", {}).get("memory")
            else int(template["create_dict"]["hardware"]["memory"])
        )

        new_desktop["create_dict"] = {
            **new_desktop["create_dict"],
            **{"reservables": create_dict.get("reservables", {"vgpus": None})},
        }
        if insert:
            with app.app_context():
                r.table("domains").insert(new_desktop).run(db.conn)
        if image:
            image_data = image
            if not image_data.get("file"):
                api_cards.update(domain_id, image_data["id"], image_data["type"])
            else:
                api_cards.upload(domain_id, image_data)
        return new_desktop

    def convert_template_to_desktop(self, data):
        data = _validate_item("template_to_desktop", data)
        if not Domain.exists(data["template_id"]):
            raise Error(
                error="not_found", description=f"Domain {data['template_id']} not found"
            )
        template = Domain(data["template_id"])

        check_user_duplicated_domain_name(data["name"], template.user, "desktop")

        # TODO: Stop derivated running desktops

        ## check if template is a duplicate from another
        if templates.is_duplicate(data["template_id"]):
            raise Error(
                "bad_request",
                "Template to desktop is a duplicate from another template",
                traceback.format_exc(),
                description_code="duplicate",
            )

        ## TODO: Permanently delete children if any

        ## TODO: Delete deployments if any

        desktop_data = self.new_from_template(
            data["name"],
            template.description,
            data["template_id"],
            template.user,
            data["template_id"],
            insert=False,
        )
        # We are updating the domain
        new_desktop_data = {
            "status": "Stopped",
            "create_dict": {
                "hardware": {"disks": template.create_dict["hardware"]["disks"]}
            },
            "xml": template.xml,
            "parents": template.parents if template.parents else [None],
        }
        # Merge the new data with the existing desktop_data
        desktop_data = {**desktop_data, **new_desktop_data}

        # Permanently delete dependants in recycle bin
        delete_dependants_recycle_bin_from_templates([data["template_id"]])

        with app.app_context():
            r.table("domains").get(data["template_id"]).update(desktop_data).run(
                db.conn
            )

        # move template disk to desktops path
        if len(template.storages) > 0:
            try:
                # TODO: change to mv once properly implemented
                template.storages[0].rsync(
                    template.user,
                    template.storages[0].directory_path_as_usage("desktop"),
                    priority="low",
                )
            except:
                raise Error(
                    "internal_server",
                    "Unable to move template disk to desktops path",
                    traceback.format_exc(),
                    description_code="unable_to_move_template_disk",
                )

        return desktop_data

    def BulkDesktops(self, payload, data):
        selected = data["allowed"]
        users = []
        desktops = []

        template = get_document("domains", data["template_id"])
        if template is None:
            raise Error("not_found", "Template to create desktops not found")

        if all(value is False for value in selected.values()):
            raise Error(
                "precondition_required",
                "Target users must be selected in order to create desktops",
                traceback.format_exc(),
            )
        if payload["role_id"] == "admin":
            if selected["roles"] is not False:
                if not selected["roles"]:
                    with app.app_context():
                        selected["roles"] = list(
                            r.table("roles").pluck("id")["id"].run(db.conn)
                        )
                for role in selected["roles"]:
                    # Can't use get_all as has no index in database
                    with app.app_context():
                        users_in_roles = list(
                            r.table("users")
                            .get_all(role, index="role")
                            .filter(lambda user: user["active"].eq(True))["id"]
                            .run(db.conn)
                        )
                    users = users + users_in_roles

            if selected["categories"] is not False:
                if not selected["categories"]:
                    with app.app_context():
                        selected["categories"] = (
                            r.table("categories").pluck("id")["id"].run(db.conn)
                        )
                with app.app_context():
                    users_in_categories = list(
                        r.table("users")
                        .get_all(r.args(selected["categories"]), index="category")
                        .filter(lambda user: user["active"].eq(True))["id"]
                        .run(db.conn)
                    )
                users = users + users_in_categories

        if selected["groups"] is not False:
            if not selected["groups"]:
                query = r.table("groups")
                if payload["role_id"] == "manager":
                    query = query.get_all(
                        payload["category_id"], index="parent_category"
                    )
                with app.app_context():
                    selected["groups"] = query["id"].run(db.conn)
            with app.app_context():
                users_in_groups = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="group")
                    .filter(lambda user: user["active"].eq(True))["id"]
                    .run(db.conn)
                )

            with app.app_context():
                users_in_secondary_groups = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="secondary_groups")
                    .filter(lambda user: user["active"].eq(True))["id"]
                    .run(db.conn)
                )
            users = users + users_in_groups + users_in_secondary_groups

        if selected["users"] is not False:
            if not selected["users"]:
                query = r.table("users")
                if payload["role_id"] == "manager":
                    query = query.get_all(payload["category_id"], index="category")
                with app.app_context():
                    selected["users"] = list(
                        query.filter(lambda user: user["active"].eq(True))
                        .pluck("id")["id"]
                        .run(db.conn)
                    )
            users = users + selected["users"]

        users = list(set(users))
        for user_id in users:
            check_user_duplicated_domain_name(data["name"], user_id)
            quotas.desktop_create(user_id)

        template["create_dict"]["hardware"]["interfaces"] = [
            i["id"] for i in template["create_dict"]["hardware"].get("interfaces", {})
        ]
        for user_id in users:
            desktop_data = {
                "name": data["name"],
                "description": data["description"],
                "template_id": data["template_id"],
                "hardware": template["create_dict"]["hardware"],
                "guest_properties": template["guest_properties"],
                "image": template["image"],
            }
            desktop_data = _validate_item("desktop_from_template", desktop_data)
            self.new_from_template(
                desktop_data["name"],
                desktop_data["description"],
                desktop_data["template_id"],
                user_id,
                desktop_data["id"],
                image=desktop_data["image"],
            )

            desktops.append(
                {
                    "id": desktop_data["id"],
                    "name": desktop_data["name"],
                    "user": user_id,
                }
            )

        return desktops

    def NewFromMedia(self, payload, data):
        with app.app_context():
            username = (
                r.table("users")
                .get(payload["user_id"])
                .pluck("username")["username"]
                .run(db.conn)
            )

        if get_document("domains", data["id"]) is not None:
            raise Error(
                "conflict",
                "Already exists a desktop with this id",
                traceback.format_exc(),
                description_code="desktop_same_id",
            )
        with app.app_context():
            xml = r.table("virt_install").get(data["xml_id"]).run(db.conn)
        if not xml:
            raise Error(
                "not_found",
                "Not found virt install xml id",
                traceback.format_exc(),
                description_code="not_found",
            )
        with app.app_context():
            media = r.table("media").get(data["media_id"]).run(db.conn)
        if not media:
            raise Error(
                "not_found",
                "Not found media id",
                traceback.format_exc(),
                description_code="not_found",
            )

        with app.app_context():
            graphics = [
                g["id"]
                for g in r.table("graphics")
                .get_all(r.args(data["hardware"]["graphics"]))
                .run(db.conn)
            ]
        if not len(graphics):
            raise Error(
                "not_found",
                "Not found graphics ids",
                traceback.format_exc(),
                description_code="not_found",
            )

        with app.app_context():
            videos = [
                v["id"]
                for v in r.table("videos")
                .get_all(r.args(data["hardware"]["videos"]))
                .run(db.conn)
            ]
        if not len(videos):
            raise Error(
                "not_found",
                "Not found videos ids",
                traceback.format_exc(),
                description_code="not_found",
            )

        with app.app_context():
            interfaces = [
                i["id"]
                for i in r.table("interfaces")
                .get_all(r.args(data["hardware"]["interfaces"]))
                .run(db.conn)
            ]
        if len(data["hardware"]["interfaces"]) != len(interfaces):
            raise Error(
                "not_found",
                "Not found interface id",
                traceback.format_exc(),
                description_code="not_found",
            )
        data["hardware"]["interfaces"] = [
            {"id": interface, "mac": gen_new_mac()}
            for interface in data["hardware"]["interfaces"]
        ]

        if data["hardware"].get("disk_size"):
            disks = [
                {
                    "bus": data["hardware"]["disk_bus"],
                    "extension": "qcow2",
                    "size": str(data["hardware"]["disk_size"]) + "G",
                }
            ]
        else:
            disks = []

        if data["hardware"].get("reservables", {"vgpus": None}).get("vgpus") == [
            "None"
        ]:
            data["hardware"]["reservables"]["vgpus"] = None

        domain = {
            "id": data["id"],
            "name": data["name"],
            "description": data["description"],
            "kind": "desktop",
            "status": "CreatingDiskFromScratch",
            "detail": "Creating desktop from existing disk and checking if it is valid (can start)",
            "user": payload["user_id"],
            "username": username,
            "category": payload["category_id"],
            "group": payload["group_id"],
            "server": False,
            "xml": None,
            "icon": (
                "fa-circle-o"
                if data["kind"] == "iso"
                else "fa-disk-o" if data["kind"] == "file" else "fa-floppy-o"
            ),
            "image": get_domain_stock_card(data["id"]),
            "os": "win",
            "guest_properties": data.get(
                "guest_properties", default_guest_properties()
            ),
            "hypervisors_pools": ["default"],
            "accessed": int(time.time()),
            "persistent": True,
            "forced_hyp": data["forced_hyp"],
            "favourite_hyp": data["favourite_hyp"],
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
            "create_dict": {
                "create_from_virt_install_xml": xml["id"],
                "hardware": {
                    "virtualization_nested": False,
                    "disks": disks,
                    "disk_bus": data["hardware"]["disk_bus"],
                    "isos": [{"id": media["id"]}],
                    "floppies": [],
                    "boot_order": data["hardware"]["boot_order"],
                    "graphics": graphics,
                    "videos": videos,
                    "interfaces": data["hardware"]["interfaces"],
                    "memory": int(data["hardware"]["memory"]),
                    "vcpus": int(data["hardware"]["vcpus"]),
                    "qos_disk_id": False,
                },
                "reservables": data["hardware"]["reservables"],
            },
            "tag": False,
            "tag_name": False,
            "tag_visible": False,
            "booking_id": False,
        }

        res = quotas.limit_user_hardware_allowed(payload, domain["create_dict"])
        if res["limited_hardware"]:
            raise Error(
                "bad_request",
                "Unauthorized hardware items: " + str(res["limited_hardware"]),
                traceback.format_exc(),
            )
        domain["create_dict"]["hardware"]["memory"] = int(
            data["hardware"]["memory"] * 1048576
        )
        with app.app_context():
            r.table("domains").insert(domain).run(db.conn)
        return domain["id"]

    def UserDesktop(self, desktop_id):
        return get_document("domains", desktop_id, ["user"])

    def Start(self, desktop_id):
        desktop_start(desktop_id)
        return desktop_id

    def Stop(self, desktop_id):
        desktop_stop(desktop_id)
        return desktop_id

    def Updating(self, desktop_id):
        desktop_updating(desktop_id)
        return desktop_id

    def Reset(self, token, request):
        desktop_id = common.DesktopFromToken(token)["id"]
        logs_domain_event_directviewer(desktop_id, "reset", request)
        desktop_reset(desktop_id)
        return token

    def Update(self, desktop_id, desktop_data, admin_or_manager=False, bulk=False):
        desktops = desktop_id if bulk else [desktop_id]
        for d in desktops:
            if desktop_data.get("image"):
                image_data = desktop_data.pop("image")

                if not image_data.get("file"):
                    api_cards.update(d, image_data["id"], image_data["type"])
                else:
                    api_cards.upload(d, image_data)

            data = copy.deepcopy(desktop_data)
            desktop = parse_domain_update(d, data, admin_or_manager)

            with app.app_context():
                r.table("domains").get(d).update(desktop).run(db.conn)

    def UpdateReservables(self, desktop_id, reservables):
        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"create_dict": {"reservables": reservables}}
            ).run(db.conn)

    def JumperUrl(self, id):
        with app.app_context():
            domain = r.table("domains").get(id).run(db.conn)
        if domain is None:
            raise Error(
                "not_found",
                "Could not get domain jumperurl as domain not exists",
                traceback.format_exc(),
                description_code="unable_to_get_domain_jumperurl",
            )
        if "jumperurl" not in domain.keys():
            return {"jumperurl": False}
        return {"jumperurl": domain["jumperurl"]}

    def JumperUrlReset(self, desktop_id, disabled=False):
        if disabled is True:
            try:
                with app.app_context():
                    r.table("domains").get(desktop_id).update({"jumperurl": False}).run(
                        db.conn
                    )
            except:
                raise Error(
                    "not_found",
                    "Unable to reset jumperurl as domain not exists",
                    traceback.format_exc(),
                    description_code="unable_to_reset_domain_jumperurl",
                )
        else:
            code = api_jumperurl_gencode()
            with app.app_context():
                r.table("domains").get(desktop_id).update({"jumperurl": code}).run(
                    db.conn
                )
            return code

    def count(self, user_id):
        with app.app_context():
            return (
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .count()
                .run(db.conn)
            )

    def check_viewers(self, data, domain):
        if data.get("guest_properties", {}).get("viewers") == None:
            data["guest_properties"] = domain["guest_properties"]
        elif not data.get("guest_properties", {}).get("viewers"):
            raise Error(
                "bad_request",
                "At least one viewer must be selected.",
                traceback.format_exc(),
                description_code="one_viewer_minimum",
            )
        hardware = {}
        if not data.get("hardware", {}).get("videos") or not data.get(
            "hardware", {}
        ).get("interfaces"):
            viewers_hardware = {}
            if not data.get("hardware", {}).get("videos"):
                viewers_hardware["videos"] = domain["create_dict"]["hardware"]["videos"]
            else:
                viewers_hardware["videos"] = data["hardware"]["videos"]

            if data.get("hardware", {}).get("interfaces") is None:
                data["hardware"] = {
                    "interfaces": [
                        interface["id"]
                        for interface in domain["create_dict"]["hardware"]["interfaces"]
                    ]
                }
                viewers_hardware["interfaces"] = [
                    interface["id"]
                    for interface in domain["create_dict"]["hardware"]["interfaces"]
                ]
            elif data.get("hardware", {}).get("interfaces") == []:
                data["hardware"] = {"interfaces": []}
                viewers_hardware["interfaces"] = []
            else:
                viewers_hardware["interfaces"] = data["hardware"]["interfaces"]

            hardware = viewers_hardware
        else:
            hardware = data["hardware"]

        viewers = data["guest_properties"]["viewers"]

        if (
            viewers.get("file_rdpgw")
            or viewers.get("browser_rdp")
            or viewers.get("file_rdpvpn")
        ) and (
            "wireguard" not in hardware["interfaces"]
            or hardware.get("interfaces") == []
        ):
            raise Error(
                "bad_request",
                "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                traceback.format_exc(),
            )

        if "none" in hardware["videos"] and (
            viewers.get("file_spice")
            or viewers.get("browser_vnc")
            or not (
                viewers.get("file_rdpgw")
                or viewers.get("browser_rdp")
                or viewers.get("file_rdpvpn")
            )
        ):
            raise Error(
                "bad_request",
                "'Only GPU' mode only works with RDP viewers. Please remove non-RDP viewers or choose another video option",
                traceback.format_exc(),
                description_code="only_works_rdp",
            )

        return data

    def check_current_plan(self, payload, desktop_id):
        fromDate = datetime.now(timezone.utc)
        toDate = fromDate + timedelta(minutes=MAX_BOOKING_TIME)
        fromDate = fromDate.strftime("%Y-%m-%dT%H:%M%z")
        toDate = toDate.strftime("%Y-%m-%dT%H:%M%z")
        current_plan = apib.get_item_bookings(
            payload,
            fromDate,
            toDate,
            "desktop",
            desktop_id,
            "availability",
        )
        if not current_plan or current_plan[0]["start"] > fromDate:
            desktop = self.Get(desktop_id=desktop_id)
            if desktop.get("tag"):
                raise Error(
                    "precondition_required",
                    "The deployment desktop reservable does not match the current plan, its deployment must be booked in order to use it",
                    description_code="needs_deployment_booking",
                )
            else:
                raise Error(
                    "precondition_required",
                    "The desktop reservable does not match the current plan",
                    description_code="current_plan_doesnt_match",
                )

        return current_plan

    def check_max_booking_date(self, payload, desktop_id):
        current_plan = self.check_current_plan(payload, desktop_id)
        # First check the users priority max time
        reservables, units, item_name = _get_reservables("desktop", desktop_id)
        users_priority = payload_priority(payload, reservables)
        if not users_priority["max_time"]:
            raise Error(
                "precondition_required",
                "Max time reached",
                description_code="bookings_max_time_reached",
            )
        priority = apib.get_min_profile_priority("desktop", desktop_id)

        forbid_time = priority["forbid_time"]
        if payload["role_id"] != "admin" and forbid_time < MIN_AUTOBOOKING_TIME:
            raise Error(
                "precondition_required",
                "There's not enough advanced time to start the desktop",
                description_code="not_enough_advanced_time",
            )
        max_time = priority["max_time"]
        available_time = int(
            (
                datetime.strptime(
                    current_plan[0]["end"], "%Y-%m-%dT%H:%M%z"
                ).astimezone(pytz.UTC)
                - datetime.now(timezone.utc)
            ).total_seconds()
            / 60
        )

        if payload["role_id"] == "admin":
            max_booking_time = min(max_time, available_time)
        else:
            max_booking_time = min(forbid_time, max_time, available_time)
        if max_booking_time >= MIN_AUTOBOOKING_TIME:
            max_booking_time = min(max_booking_time, MAX_BOOKING_TIME)

            max_booking_date = datetime.strftime(
                datetime.now(timezone.utc) + timedelta(minutes=max_booking_time),
                "%Y-%m-%dT%H:%M%z",
            )
            return json.dumps({"max_booking_date": max_booking_date})
        else:
            desktop = self.Get(desktop_id=desktop_id)
            if desktop.get("tag"):
                raise Error(
                    "precondition_required",
                    "There's not enough advanced time to start the deployment desktop, its deployment must be booked in order to use it",
                    description_code="needs_deployment_booking",
                )
            raise Error(
                "precondition_required",
                "There's not enough time to start the desktop",
                description_code="not_enough_time_to_start",
            )

    def validate_desktop_update(self, data, domain_id):
        desktop = self.Get(domain_id)
        data["id"] = domain_id
        if data.get("name"):
            check_user_duplicated_domain_name(
                data["name"], desktop["user"], desktop.get("kind"), data["id"]
            )
        if data.get("hardware") or data.get("guest_properties"):
            self.check_viewers(data, desktop)
        if not "server" in data and desktop.get("status") not in ["Failed", "Stopped"]:
            raise Error(
                "precondition_required",
                "Desktops only can be edited when stopped or failed",
                traceback.format_exc(),
            )
        if (
            desktop.get("server_autostart")
            and (desktop["server_autostart"] not in data or "server" not in data)
            and desktop.get("status") != "Failed"
        ):
            raise Error(
                "precondition_required",
                "Autostart servers can't be edited",
                traceback.format_exc(),
            )

        if data.get("server_autostart") is True and (
            data.get("server") is False
            or (data.get("server") is None and not desktop.get("server"))
        ):
            raise Error(
                "precondition_required",
                "Non-server desktops can't be set to autostart",
                traceback.format_exc(),
            )

        if desktop.get("create_dict", {}).get("reservables", {}).get("vgpus") and (
            data.get("server")
        ):
            raise Error(
                "precondition_required",
                "Servers can not have a bookable item",
                traceback.format_exc(),
            )
        if data.get("hardware", {}).get("reservables", {}).get("vgpus") and data[
            "hardware"
        ]["reservables"] != desktop.get("hardware", {}).get("reservables"):
            with app.app_context():
                vgpu_profiles = list(r.table("reservables_vgpus")["id"].run(db.conn))
            for desktop_profile in data["hardware"]["reservables"].get("vgpus"):
                if desktop_profile not in vgpu_profiles:
                    raise Error("not_found", "vGPU not found: " + desktop_profile)

    def change_status(self, current_status, target_status):
        with app.app_context():
            r.table("domains").get_all(
                ["desktop", current_status], index="kind_status"
            ).update({"status": target_status}).run(db.conn)

    def change_status_category(self, category, current_status, target_status):
        with app.app_context():
            r.table("domains").get_all(
                ["desktop", current_status, category], index="kind_status_category"
            ).update({"status": target_status}).run(db.conn)

    def update_storage(self, domain_id, new_storage_id):
        with app.app_context():
            domain = r.table("domains").get(domain_id).run(db.conn)
        if not domain:
            raise Error(
                "not_found",
                "Domain not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        if domain["status"] not in ["Stopped", "Maintenance"]:
            raise Error(
                "precondition_required",
                "Desktop must be stopped to change storage",
                traceback.format_exc(),
            )
        if domain["kind"] == "desktop":
            with app.app_context():
                r.table("domains").get(domain_id).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "disks": [
                                    {
                                        "storage_id": new_storage_id,
                                    }
                                ]
                            }
                        }
                    }
                ).run(db.conn)

        return domain_id

    def set_desktops_maintenance(
        self, payload, storage_id, action, domains=None, batch_size=250
    ):
        if domains == None:
            domains = get_storage_derivatives(storage_id)

        for domain_id in domains:
            ownsDomainId(payload, domain_id)
        for i in range(0, len(domains), batch_size):
            batch_ids = domains[i : i + batch_size]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"status": "Maintenance", "current_action": action}
                ).run(db.conn)


def check_template_status(template_id=None, template=None):
    if template_id:
        template = templates.Get(template_id)

    if template["status"] == "Failed":
        raise Error(
            "bad_request",
            "Can't create a desktop with a Failed template.",
            traceback.format_exc(),
            description_code="template_failed",
        )


def domain_template_tree(domain_id):
    try:
        with app.app_context():
            parents_ids = (
                r.table("domains")
                .get(domain_id)
                .pluck("parents")["parents"]
                .run(db.conn)
            )
    except:
        return []
    with app.app_context():
        parents = list(
            r.table("domains")
            .get_all(r.args(parents_ids))
            .merge(
                lambda domain: {
                    "category_name": r.table("categories").get(domain["category"])[
                        "name"
                    ],
                    "group_name": r.table("groups").get(domain["group"])["name"],
                    "parents_count": r.expr(domain["parents"]).default([]).count(),
                }
            )
            .order_by(r.asc("parents_count"))
            .pluck(
                "id",
                "name",
                "user",
                "username",
                "category_name",
                "group_name",
                "parents_count",
            )
            .run(db.conn)
        )
    return parents


def get_desktops_with_resource(table, item):
    if table == "media":
        return get_media_domains(item["id"])
    elif table == "reservables_vgpus":
        return api_ri.check_desktops_with_profile("gpus", item["id"])
    elif table in ["interfaces", "boots", "videos"]:
        with app.app_context():
            return list(
                r.table("domains")
                .get_all(item["id"], index="boot_order" if table == "boots" else table)
                .eq_join("user", r.table("users"))
                .pluck(
                    {
                        "left": {"id": True},
                        "right": {
                            "id": True,
                            "group": True,
                            "category": True,
                            "role": True,
                        },
                    }
                )
                .map(
                    lambda doc: {
                        "id": doc["left"]["id"],
                        "user_data": {
                            "role_id": doc["right"]["role"],
                            "category_id": doc["right"]["category"],
                            "group_id": doc["right"]["group"],
                            "user_id": doc["right"]["id"],
                        },
                    }
                )
                .run(db.conn)
            )


def unassign_resource_from_desktops_and_deployments(table, item):
    if table == "qos_disk":
        with app.app_context():
            r.table("domains").get_all(item["id"], index="qos_disk_id").update(
                {"create_dict": {"hardware": {"qos_disk_id": False}}}
            ).run(db.conn)
        return []

    domains = get_desktops_with_resource(table, item)
    not_allowed_desktops = []
    deployments = get_deployments_with_resource(table, item)
    not_allowed_deployments = []

    if item.get("allowed"):
        for domain in domains:
            isAllowed = api_allowed.is_allowed(domain.pop("user_data"), item, table)
            if not isAllowed:
                not_allowed_desktops.append(domain["id"])
        for deployment in deployments:
            isAllowed = api_allowed.is_allowed(deployment.pop("user_data"), item, table)
            if not isAllowed:
                not_allowed_deployments.append(deployment["id"])
    else:
        not_allowed_desktops = [domain.get("id") for domain in domains]
        not_allowed_deployments = [deployment["id"] for deployment in deployments]

    if table == "media":
        with app.app_context():
            r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                {
                    "create_dict": {
                        "hardware": {
                            "isos": r.row["create_dict"]["hardware"]["isos"].filter(
                                lambda media: media["id"].ne(item["id"])
                            )
                        }
                    }
                }
            ).run(db.conn)
        with app.app_context():
            r.table("deployments").get_all(r.args(not_allowed_deployments)).update(
                {
                    "create_dict": {
                        "hardware": {
                            "isos": r.row["create_dict"]["hardware"]["isos"].filter(
                                lambda media: media["id"].ne(item["id"])
                            )
                        }
                    }
                }
            ).run(db.conn)

    elif table == "reservables_vgpus":
        api_ri.deassign_desktops_with_gpu(
            "gpus", item["id"], desktops=not_allowed_desktops
        )
    elif table == "interfaces":
        if item["id"] == "wireguard":
            with app.app_context():
                r.table("domains").get_all(r.args(not_allowed_desktops)).replace(
                    r.row.without(
                        {
                            "guest_properties": {
                                "viewers": {
                                    "browser_rdp": True,
                                    "file_rdpgw": True,
                                    "file_rdpvpn": True,
                                }
                            },
                        }
                    )
                ).run(db.conn)
            with app.app_context():
                r.table("deployments").get_all(r.args(not_allowed_deployments)).replace(
                    r.row.without(
                        {
                            "create_dict": {
                                "guest_properties": {
                                    "viewers": {
                                        "browser_rdp": True,
                                        "file_rdpgw": True,
                                        "file_rdpvpn": True,
                                    }
                                },
                            }
                        }
                    )
                ).run(db.conn)
        with app.app_context():
            r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                {
                    "create_dict": {
                        "hardware": {
                            "interfaces": r.row["create_dict"]["hardware"][
                                "interfaces"
                            ].filter(lambda interface: interface["id"].ne(item["id"]))
                        }
                    }
                }
            ).run(db.conn)
        with app.app_context():
            r.table("deployments").get_all(r.args(not_allowed_deployments)).update(
                {
                    "create_dict": {
                        "hardware": {
                            "interfaces": r.row["create_dict"]["hardware"][
                                "interfaces"
                            ].difference([item["id"]])
                        }
                    }
                }
            ).run(db.conn)
    elif table in ["boots", "videos"]:
        fields = {
            "boots": "boot_order",
            "videos": "videos",
        }
        with app.app_context():
            r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                {
                    "create_dict": {
                        "hardware": {
                            fields[table]: r.row["create_dict"]["hardware"][
                                fields[table]
                            ].difference([item["id"]])
                        }
                    }
                }
            ).run(db.conn)
        with app.app_context():
            r.table("deployments").get_all(r.args(not_allowed_desktops)).update(
                {
                    "create_dict": {
                        "hardware": {
                            fields[table]: r.row["create_dict"]["hardware"][
                                fields[table]
                            ].difference([item["id"]])
                        }
                    }
                }
            ).run(db.conn)
    return not_allowed_desktops


def get_deployments_with_resource(table, item):
    if table in ["media", "reservables_vgpus", "interfaces", "boots", "videos"]:
        indexes = {
            "media": "isos",
            "reservables_vgpus": "vgpus",
            "interfaces": "interfaces",
            "boots": "boot_order",
            "videos": "videos",
        }
        with app.app_context():
            return list(
                r.table("deployments")
                .get_all(item["id"], index=indexes[table])
                .eq_join("user", r.table("users"))
                .pluck(
                    {
                        "left": {"id": True},
                        "right": {
                            "id": True,
                            "group": True,
                            "category": True,
                            "role": True,
                        },
                    }
                )
                .map(
                    lambda doc: {
                        "id": doc["left"]["id"],
                        "user_data": {
                            "role_id": doc["right"]["role"],
                            "category_id": doc["right"]["category"],
                            "group_id": doc["right"]["group"],
                            "user_id": doc["right"]["id"],
                        },
                    }
                )
                .run(db.conn)
            )
    else:
        raise Error(
            "forbidden",
            "Table without deployments",
            traceback.format_exc(),
        )


def get_unused_desktops(from_deployments=False):
    """
    Retrieve a list of unused desktops that have not been accessed considering the specified cutoff time defined in the unused_item_timeout table.

    :return: A list of desktops that have not been accessed within the specified cutoff_time.
    :rtype: list
    """

    desktops = []
    start = absolute_start = time.time()

    with app.app_context():
        users_with_desktops = list(
            r.table("domains")
            .get_all(
                r.args(
                    [
                        ["desktop", "Stopped"],
                        ["desktop", "Maintenance"],
                        ["desktop", "Failed"],
                    ]
                ),
                index="kind_status",
            )
            .pluck("user")
            .distinct()["user"]
            .run(db.conn)
        )

    log.debug(
        "api_desktops_persistent get unused desktops: Retrieved users with desktops in %s seconds",
        time.time() - start,
    )

    for user in users_with_desktops:
        start = time.time()
        try:
            payload = gen_payload_from_user(user)
            user_timeout_rule = get_unused_item_timeout(
                payload, "send_unused_desktops_to_recycle_bin"
            )
        except TypeError as e:
            # If the user does not exist then send to the recycle bin all of its deployments
            log.error(
                "api_desktops_persistent get unused desktops: Could not generate payload for user %s",
                user,
            )
            user_timeout_rule = {"cutoff_time": 0}

        if user_timeout_rule is False or user_timeout_rule["cutoff_time"] is None:
            continue
        log.debug(
            "api_desktops_persistent get unused desktops: User %s applied rule %s",
            user,
            user_timeout_rule,
        )
        cutoff_time = timedelta(days=user_timeout_rule["cutoff_time"] * 30)
        cutoff_timestamp = (datetime.now() - cutoff_time).timestamp()
        query = r.row["accessed"] < cutoff_timestamp
        if not from_deployments:
            query = query & (r.row["tag"] == False)

        with app.app_context():
            user_desktops = list(
                r.table("domains")
                .get_all(
                    r.args(
                        [
                            ["desktop", "Stopped", user],
                            ["desktop", "Maintenance", user],
                            ["desktop", "Failed", user],
                        ]
                    ),
                    index="kind_status_user",
                )
                .filter(query)
                .pluck("id", "user", "name", "accessed")
                .run(db.conn)
            )
        log.debug(
            "api_desktops_persistent get unused desktops: Retrieved user unused desktops and applied rule in %s seconds",
            time.time() - start,
        )
        desktops += user_desktops

    log.debug(
        "api_desktops_persistent get unused desktops: Retrieved users with desktops in %s seconds",
        time.time() - absolute_start,
    )

    return desktops
