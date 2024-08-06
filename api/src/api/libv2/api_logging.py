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

import logging as log
import traceback
from time import time
from uuid import uuid4

import gevent
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def action_owner(action_owner, item_owner, direct_viewer=False):
    if action_owner == "isard-scheduler":
        return "isard-scheduler"
    if direct_viewer:
        return "desktop-directviewer"
    if not action_owner:
        return "isard-engine"
    if str(action_owner) == str(item_owner):
        return "desktop-owner"
    return "system-admins"


def action_owner_deploy(action_owner, item_owner, tag=None, direct_viewer=False):
    if action_owner == "isard-scheduler":
        return "isard-scheduler", None
    if direct_viewer:
        return "desktop-directviewer", None
    if not action_owner:
        return "isard-engine", None
    if action_owner == item_owner:
        return "desktop-owner", action_owner
    if tag:
        with app.app_context():
            try:
                deploy = (
                    r.table("deployments")
                    .get(tag)
                    .default({"user": None, "name": ""})
                    .pluck("user", "name", "co_owners")
                    .run(db.conn)
                )
            except:
                log.warning("Unable to fetch deployment owner for logs")
                log.debug(traceback.format_exc())
                return None, None
        if deploy["user"] == action_owner:
            return "deployment-owner", deploy["name"]
        elif action_owner in deploy["co_owners"]:
            return "deployment-co-owner", deploy["name"]
    return "system-admins", action_owner


def parse_user_request(user_request=None):
    if user_request:
        return {
            "request_ip": user_request.headers.environ["HTTP_X_FORWARDED_FOR"],
            "request_agent_browser": user_request.user_agent.browser,
            "request_agent_platform": user_request.user_agent.platform,
            "request_agent_version": user_request.user_agent.version,
        }
    return {
        "request_ip": None,
        "request_agent_browser": None,
        "request_agent_platform": None,
        "request_agent_version": None,
    }


# START DESKTOP
def logs_domain_start_api(dom_id, action_user=None, user_request=None):
    gevent.spawn(
        _logs_domain_start,
        dom_id,
        user_request=parse_user_request(user_request),
        action_user=action_user,
    )


def logs_domain_start_directviewer(dom_id, user_request=None):
    gevent.spawn(
        _logs_domain_start,
        dom_id,
        user_request=parse_user_request(user_request),
        direct_viewer=True,
    )


def _logs_domain_start(
    dom_id,
    user_request,
    action_user=None,
    direct_viewer=False,
    server_hyp_started=False,
):
    # Who can start a desktop:
    # - User: desktop-owner|deployment-owner|deployment-co-owner|system-admins
    # - Desktop direct viewer access: desktop-directviewer
    start_logs_id = str(uuid4())
    try:
        with app.app_context():
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
    try:
        with app.app_context():
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
        if server_hyp_started:
            data["started_time"] = r.epoch_time(time())
            data["hyp_started"] = server_hyp_started
        data = {**data, **user_request}
    except:
        log.warning("Unable to fetch log data for start logs id")
        log.debug(traceback.format_exc())
        return
    if domain.get("create_dict", {}).get("reservables", {}).get("vgpus"):
        data["hardware_bookables_vgpus"] = domain["create_dict"]["reservables"]["vgpus"]
        if domain.get("booking_id"):
            with app.app_context():
                try:
                    booking = (
                        r.table("bookings")
                        .get(domain.get("booking_id"))
                        .pluck("start", "end")
                        .run(db.conn)
                    )
                    data["booking_id"] = domain["booking_id"]
                    data["booking_start"] = booking["start"]
                    data["booking_end"] = booking["end"]
                except:
                    log.warning("Unable to fetch booking data for start logs id")
                    log.debug(traceback.format_exc())
    if domain.get("forced_hyp"):
        data["hyp_forced"] = domain["forced_hyp"]
    if domain.get("favourite_hyp"):
        data["hyp_favourite"] = domain["favourite_hyp"]
    with app.app_context():
        r.table("logs_desktops").insert(data, durability="soft").run(db.conn)


def logs_domain_start_engine(start_logs_id, dom_id, hyp_started=None):
    gevent.spawn(
        _logs_domain_start_engine,
        start_logs_id,
        dom_id,
        hyp_started=hyp_started,
    )


def _logs_domain_start_engine(start_logs_id, dom_id, hyp_started=None):
    if not start_logs_id:
        # It could be a server desktop started by engine
        _logs_domain_start(dom_id, parse_user_request(), server_hyp_started=hyp_started)
        return
    # It has a logs_desktops id, try to update it
    # When user started, it will have a valid uuid and update should work
    # When engine started, it could fail because of old id. There is no way to know
    # if it is and old id or a current id. So we try to update it and if it fails
    # we add it as a new log
    result = {}
    with app.app_context():
        try:
            result = (
                r.table("logs_desktops")
                .get(start_logs_id)
                .update(
                    {"started_time": r.epoch_time(time()), "hyp_started": hyp_started},
                    durability="soft",
                )
                .run(db.conn)
            )
        except:
            log.warning("Unable to update start time in logs")
            log.debug(traceback.format_exc())
    if result.get("skipped"):
        _logs_domain_start(dom_id, parse_user_request(), server_hyp_started=hyp_started)


# STOP DESKTOP
def logs_domain_stop_api(dom_id, action_user=None):
    gevent.spawn(_logs_domain_stop_api, dom_id, action_user=action_user)


def _logs_domain_stop_api(desktop_id, action_user):
    with app.app_context():
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
    with app.app_context():
        try:
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
    gevent.spawn(_logs_domain_stop_engine, start_logs_id, new_status=new_status)


def _logs_domain_stop_engine(start_logs_id, new_status=""):
    if not start_logs_id:
        log.warning("Engine stop domain without start_logs_id")
        return
    with app.app_context():
        try:
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
    with app.app_context():
        try:
            r.table("domains").get(desktop_id).update(
                {"start_logs_id": None}, durability="soft"
            ).run(db.conn)
        except:
            log.warning("Unable to remove start_logs_id from domain")
            log.debug(traceback.format_exc())


# UPDATE EVENTS (unused now)


def logs_domain_event_viewer(domain_id, action_user, viewer_type, user_request=None):
    gevent.spawn(
        _logs_domain_event_viewer,
        domain_id,
        action_user,
        viewer_type,
        user_request=user_request,
    )


def _logs_domain_event_viewer(domain_id, action_user, viewer_type, user_request=None):
    with app.app_context():
        try:
            start_logs_id = (
                r.table("domains").get(domain_id).pluck("start_logs_id").run(db.conn)
            )["start_logs_id"]
        except:
            log.warning(
                "Unable to update viewer event logs for domain: " + str(domain_id)
            )
            log.debug(traceback.format_exc())
            return
    _logs_domain_event(
        start_logs_id,
        "viewer",
        action_user,
        viewer_type=viewer_type,
        user_request=parse_user_request(user_request),
    )


def logs_domain_event_directviewer(
    domain_id, action_user, viewer_type=None, user_request=None
):
    gevent.spawn(
        _logs_domain_event_directviewer,
        domain_id,
        action_user,
        viewer_type,
        user_request=user_request,
    )


def _logs_domain_event_directviewer(
    domain_id, action_user, viewer_type=None, user_request=None
):
    with app.app_context():
        try:
            start_logs_id = (
                r.table("domains").get(domain_id).pluck("start_logs_id").run(db.conn)
            )["start_logs_id"]
        except:
            log.warning(
                "Unable to update directviewer event logs for domain: " + str(domain_id)
            )
            log.debug(traceback.format_exc())
            return
    _logs_domain_event(
        start_logs_id,
        "directviewer",
        action_user,
        viewer_type=viewer_type,
        user_request=parse_user_request(user_request),
    )


def _logs_domain_event(
    start_logs_id,
    event,
    action_user=None,
    viewer_type="",
    user_request=None,
):
    with app.app_context():
        try:
            r.table("logs_desktops").get(start_logs_id).update(
                {
                    "events": r.row["events"].append(
                        {
                            **user_request,
                            **{
                                "event": event,
                                "time": r.epoch_time(time()),
                                "action_user": action_user,
                                "viewer_type": viewer_type,
                            },
                        }
                    )
                },
                durability="soft",
            ).run(db.conn)
        except:
            log.warning("Unable to update " + str(event) + " event logs")
            log.debug(traceback.format_exc())
