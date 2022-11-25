#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import json
import logging as log
import traceback

from rethinkdb.errors import ReqlDriverError

from ..libv2.api_desktops_common import ApiDesktopsCommon
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)
common = ApiDesktopsCommon()

import threading

from flask import request
from flask_socketio import join_room, leave_room

from .. import socketio
from .api_cards import ApiCards

api_cards = ApiCards()

threads = {}

from flask import request

from .._common.api_exceptions import Error
from ..auth.tokens import Error, get_token_payload
from .api_scheduler import Scheduler
from .helpers import (
    _is_frontend_desktop_status,
    _parse_deployment_desktop,
    _parse_desktop,
)

scheduler = Scheduler()


class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("domains")
                        .pluck(
                            [
                                "id",
                                "name",
                                "icon",
                                "image",
                                "user",
                                "status",
                                "description",
                                "parents",
                                "persistent",
                                "os",
                                "tag_visible",
                                "viewer",
                                "guest_properties",
                                {
                                    "create_dict": {
                                        "hardware": ["interfaces", "videos"],
                                        "reservables": True,
                                    }
                                },
                                "kind",
                                "tag",
                                "progress",
                                "jumperurl",
                                "booking_id",
                                "scheduled",
                                "server",
                                "accessed",
                            ]
                        )
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break

                        if c["new_val"] == None:
                            event = "delete"
                            try:
                                if c["old_val"]["image"]["type"] == "user":
                                    api_cards.delete_card(c["old_val"]["image"]["id"])
                            except:
                                log.warning(
                                    "Unable to delete card "
                                    + c["old_val"]["image"]["id"]
                                )
                            if c["old_val"]["kind"] != "desktop":
                                item = "template"
                            else:
                                item = "desktop"
                            data = c["old_val"]
                        else:
                            if not _is_frontend_desktop_status(c["new_val"]["status"]):
                                continue

                            if c["new_val"]["kind"] != "desktop":
                                item = "template"
                            else:
                                item = "desktop"

                            if c["old_val"] == None:
                                # New
                                event = "add"
                            else:
                                if not c["old_val"].get("tag_visible") and c[
                                    "new_val"
                                ].get("tag_visible"):
                                    event = "add"
                                else:
                                    # Update
                                    event = "update"
                                    if c["old_val"]["status"] in [
                                        "Stopping",
                                        "Shutting-down",
                                    ] and c["new_val"]["status"] in [
                                        "Stopped",
                                        "Failed",
                                    ]:
                                        scheduler.remove_desktop_timeouts(
                                            c["new_val"]["id"]
                                        )
                            data = c["new_val"]

                        socketio.emit(
                            item + "_" + event,
                            json.dumps(
                                data if item != "desktop" else _parse_desktop(data)
                            ),
                            namespace="/userspace",
                            room=data["user"],
                        )
                        if (
                            event == "update"
                            and item == "desktop"
                            and data.get("jumperurl")
                            and c.get("new_val", {}).get("status") == "Started"
                            and c.get("new_val", {}).get("viewer", {}).get("tls", {})
                        ):
                            viewers = common.DesktopViewerFromToken(
                                data.get("jumperurl"),
                                start_desktop=False,
                            )
                            if viewers is not None:
                                viewer_data = {
                                    "desktopId": viewers.pop("desktopId"),
                                    "jwt": viewers.pop("jwt", None),
                                    "vmName": viewers.pop("vmName", None),
                                    "vmDescription": viewers.pop("vmDescription", None),
                                    "vmState": viewers.pop("vmState"),
                                    "viewers": viewers,
                                }
                                socketio.emit(
                                    "directviewer_update",
                                    json.dumps(viewer_data),
                                    namespace="/userspace",
                                    room=data["id"],
                                )
                        # Event delete for users when tag becomes hidden
                        if not data.get("tag_visible", True):
                            if c["old_val"] is None or c["old_val"].get("tag_visible"):
                                socketio.emit(
                                    "desktop_delete",
                                    json.dumps(
                                        data
                                        if item != "desktop"
                                        else _parse_desktop(data)
                                    ),
                                    namespace="/userspace",
                                    room=data["user"],
                                )

                        ## Tagged desktops update/add new data
                        if data.get("tag", False):
                            deployment_id = data.get("tag")
                            deployment_user = (
                                r.table("deployments")
                                .get(deployment_id)
                                .pluck("user")
                                .run(db.conn)["user"]
                            )

                            if event == "delete":
                                socketio.emit(
                                    "deploymentdesktop_delete",
                                    json.dumps(data),
                                    namespace="/userspace",
                                    room=deployment_user,
                                )

                            if event == "add" and not c.get("old_val"):
                                socketio.emit(
                                    "deploymentdesktop_add",
                                    json.dumps(
                                        _parse_deployment_desktop(data, deployment_user)
                                    ),
                                    namespace="/userspace",
                                    room=deployment_user,
                                )

                            if event == "update":
                                socketio.emit(
                                    "deploymentdesktop_update",
                                    json.dumps(
                                        _parse_deployment_desktop(data, deployment_user)
                                    ),
                                    namespace="/userspace",
                                    room=deployment_user,
                                )

                            deployment = (
                                r.table("deployments")
                                .get(deployment_id)
                                .pluck(
                                    "id",
                                    "name",
                                    "user",
                                    {"create_dict": {"tag_visible", "name"}},
                                )
                                .merge(
                                    lambda d: {
                                        "totalDesktops": r.table("domains")
                                        .get_all(d["id"], index="tag")
                                        .count(),
                                        "startedDesktops": r.table("domains")
                                        .get_all(d["id"], index="tag")
                                        .filter({"status": "Started"})
                                        .count(),
                                        "visible": d["create_dict"]["tag_visible"],
                                        "desktop_name": d["create_dict"]["name"],
                                    }
                                )
                                .run(db.conn)
                            )
                            # Event to deployment view (list of desktops)
                            socketio.emit(
                                "deployments_update",
                                json.dumps(deployment),
                                namespace="/userspace",
                                room=deployment_user,
                            )

            except ReqlDriverError:
                print("DomainsThread: Rethink db connection lost!")
                log.error("DomainsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("DomainsThread internal error: restarting")
                log.error("DomainsThread internal error: restarting")
                log.error(traceback.format_exc())
                time.sleep(2)


def start_domains_thread():
    global threads
    if "domains" not in threads:
        threads["domains"] = None
    if threads["domains"] == None:
        threads["domains"] = DomainsThread()
        threads["domains"].daemon = True
        threads["domains"].start()
        log.info("DomainsThread Started")


# Domains namespace
@socketio.on("connect", namespace="/userspace")
def socketio_users_connect():
    payload = get_token_payload(request.args.get("jwt"))
    if payload.get("desktop_id"):
        try:
            with app.app_context():
                list(r.table("domains").get(payload.get("desktop_id")).run(db.conn))[0]
        except:
            raise Error(
                "not_found",
                "Websocket direct viewer desktop_id "
                + str(payload.get("desktop_id"))
                + " not found",
                traceback.format_exc(),
            )
        join_room(payload.get("desktop_id"))
        log.debug(
            "Websocket direct viewer for desktop_id "
            + str(payload.get("desktop_id"))
            + " joined"
        )
    elif payload.get("user_id"):
        join_room(payload["user_id"])
        log.debug("Websocket user_id " + payload["user_id"] + " joined")
    else:
        raise Error(
            "not_found",
            "Websocket connection incorrect data",
            traceback.format_exc(),
        )


@socketio.on("disconnect", namespace="/userspace")
def socketio_domains_disconnect(data=False):
    try:
        payload = get_token_payload(request.args.get("jwt"))
        if payload.get("desktop_id"):
            leave_room(payload.get("desktop_id"))
        else:
            leave_room(payload["user_id"])
    except:
        log.debug(traceback.format_exc())
