#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import traceback
from time import time
from uuid import uuid4

from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def action_owner(action_owner, item_owner, direct_viewer=False):
    if action_owner == "isard-scheduler":
        return "isard-scheduler"
    if not action_owner:
        return "isard-engine"
    if direct_viewer:
        return "desktop-directviewer"
    if str(action_owner) == str(item_owner):
        return "desktop-owner"
    return "system-admins"


def action_owner_deploy(action_owner, item_owner, tag=None, direct_viewer=False):
    if action_owner == "isard-scheduler":
        return "isard-scheduler", None
    if not action_owner:
        return "isard-engine", None
    if direct_viewer:
        return "desktop-directviewer", None
    if tag:
        with app.app_context():
            try:
                deploy = (
                    r.table("deployments")
                    .get(tag)
                    .default({"user": None, "name": ""})
                    .pluck("user", "name")
                    .run(db.conn)
                )
            except:
                log.warning("Unable to fetch deployment owner for logs")
                log.debug(traceback.format_exc())
                return None, None
        if deploy["user"] == action_owner:
            return "deployment-owner", deploy["name"]
    if str(action_owner) == str(item_owner):
        return "desktop-owner", action_owner
    return "system-admins", action_owner


# START DESKTOP
def logs_domain_start_api(dom_id, action_user=None):
    _logs_domain_start(dom_id, action_user)


def logs_domain_start_directviewer(dom_id):
    _logs_domain_start(dom_id, direct_viewer=True)


def _logs_domain_start(dom_id, action_user=None, direct_viewer=False):
    # Who can start a desktop:
    # - User: desktop-owner|deployment-owner|system-admins
    # - Desktop direct viewer access: desktop-directviewer
    start_logs_id = str(uuid4())
    with app.app_context():
        try:
            domain = (
                r.table("domains")
                .get(dom_id)
                .update(
                    {"start_logs_id": start_logs_id},
                    return_changes="always",
                    durability="soft",
                )
                .run(db.conn)["changes"][0]["old_val"]
            )
        except:
            log.warning("Unable to update domain with start log id")
            log.debug(traceback.format_exc())
            return
    if domain.get("tag"):
        action_by, deployment_name = action_owner_deploy(
            action_user, domain["user"], domain.get("tag"), direct_viewer
        )
        if not action_by or not deployment_name:
            return
    else:
        action_by = action_owner(action_user, domain["user"], direct_viewer)
    with app.app_context():
        try:
            user = (
                r.table("users")
                .get(domain["user"])
                .pluck("role", "category", "group")
                .merge(
                    lambda user: {
                        "category_name": r.table("categories").get(user["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(user["group"])["name"],
                    }
                )
                .run(db.conn)
            )
        except:
            log.warning("Unable to fetch user data for start logs id")
            log.debug(traceback.format_exc())
            return
    try:
        data = {
            "id": start_logs_id,
            "starting_time": r.epoch_time(time()),
            "starting_by": action_by,
            "starting_user": action_user,
            "desktop_id": dom_id,
            "desktop_name": domain.get("name"),
            "desktop_template_hierarchy": domain.get("parents"),
            "owner_user_id": domain.get("user"),
            "owner_user_name": domain.get("username"),
            "owner_category_id": domain.get("category"),
            "owner_category_name": user["category_name"],
            "owner_group_id": domain.get("group"),
            "owner_group_name": user["group_name"],
            "owner_role_id": user["role"],
            "hardware_vcpus": domain.get("create_dict", {})
            .get("hardware", {})
            .get("vcpus"),
            "hardware_memory": domain.get("create_dict", {})
            .get("hardware", {})
            .get("memory"),
            "events": [],
        }
        if domain.get("tag"):
            data["deployment_id"] = domain.get("tag")
            data["deployment_name"] = deployment_name
        if domain.get("create_dict", {}).get("reservables", {}).get("vgpus"):
            data["hardware_bookables_vgpus"]: domain["create_dict"]["reservables"][
                "vgpus"
            ]
            if domain.get("booking_id"):
                with app.app_context():
                    booking = (
                        r.table("bookings")
                        .get(domain.get("booking_id"))
                        .pluck("start", "end")
                        .run(db.conn)
                    )
                data["booking_id"] = domain["booking_id"]
                data["booking_start"] = booking["start"]
                data["booking_end"] = booking["end"]
        if domain.get("forced_hyp"):
            data["hyp_forced"] = domain["forced_hyp"]
        if domain.get("favourite_hyp"):
            data["hyp_favourite"] = domain["favourite_hyp"]
    except:
        log.warning("Unable to parse all data at user start logs")
        log.debug(traceback.format_exc())
        return
    with app.app_context():
        r.table("logs_desktops").insert(data, durability="soft").run(db.conn)


def logs_domain_start_engine(start_logs_id, hyp_started=None):
    # When engine actually started the domain in the hypervisor
    with app.app_context():
        try:
            r.table("logs_desktops").get(start_logs_id).update(
                {"started_time": r.epoch_time(time()), "hyp_started": hyp_started},
                durability="soft",
            ).run(db.conn)
        except:
            log.warning("Unable to update engine desktop start event")
            log.debug(traceback.format_exc())


# STOP DESKTOP
def logs_domain_stop_api(desktop_id, action_user):
    try:
        domain = (
            r.table("domains")
            .get(desktop_id)
            .pluck("start_logs_id", "tag", "user")
            .run(db.conn)
        )
    except:
        log.warning("Unable to get desktop start_logs_id")
        log.debug(traceback.format_exc())
        return
    if not domain.get("start_logs_id"):
        log.warning("User stop domain without start_logs_id")
        return
    if domain.get("tag"):
        action_by, deployment_name = action_owner_deploy(
            action_user, domain["user"], domain.get("tag")
        )
        if not action_by or not deployment_name:
            return
    else:
        action_by = action_owner(action_user, domain["user"])
    try:
        with app.app_context():
            r.table("logs_desktops").get(domain.get("start_logs_id")).update(
                {
                    "stopping_time": r.epoch_time(time()),
                    "stopping_by": action_by,
                    "stopping_user": action_user,
                },
                durability="soft",
            ).run(db.conn)
    except:
        log.warning("Unable to update event stop in logs")
        log.debug(traceback.format_exc())


def logs_domain_stop_engine(start_logs_id, new_status=""):
    if not start_logs_id:
        log.warning("Engine stop domain without start_logs_id")
        return
    try:
        with app.app_context():
            desktop = (
                r.table("logs_desktops")
                .get(start_logs_id)
                .update(
                    r.branch(
                        r.row.has_fields("stopping_time"),
                        {
                            "stopped_time": r.epoch_time(time()),
                            "stopped_status": new_status,
                        },
                        {
                            "stopped_time": r.epoch_time(time()),
                            "stopped_by": "isard-engine",
                            "stopped_status": new_status,
                        },
                    ),
                    return_changes="always",
                    durability="soft",
                )
                .run(db.conn)
            )
            if not desktop:
                log.warning(
                    "Unable to update stopped time at desktop: "
                    + str(desktop_id)
                    + " as it does not exist anymore"
                )
                return
            desktop_id = desktop["changes"][0]["new_val"]["desktop_id"]
    except:
        log.warning("Unable to update stopped time for desktop")
        log.debug(traceback.format_exc())
        return
    try:
        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"start_logs_id": None}, durability="soft"
            ).run(db.conn)
    except:
        log.warning("Unable to remove start_logs_id from domain")
        log.debug(traceback.format_exc())


# UPDATE EVENTS (unused now)


def logs_domain_event_viewer(start_logs_id, action_user, viewer_type):
    _logs_domain_event(start_logs_id, "viewer", action_user, data=viewer_type)


def logs_domain_event_directviewer(start_logs_id, viewer_type):
    _logs_domain_event(start_logs_id, "directviewer", data=viewer_type)


def _logs_domain_event(
    start_logs_id,
    event,
    action_user=None,
    data="",
):

    try:
        with app.app_context():
            log.debug(
                r.table("logs_desktops")
                .get(start_logs_id)
                .update(
                    {
                        "events": r.row["events"].append(
                            {
                                "event": event,
                                "time": r.epoch_time(time()),
                                "action_user": action_user,
                                "data": data,
                            }
                        )
                    },
                    durability="soft",
                )
                .run(db.conn)
            )
    except:
        log.warning("Unable to update " + str(event) + " event logs")
        log.debug(traceback.format_exc())
