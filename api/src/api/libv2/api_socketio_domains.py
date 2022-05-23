#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import os
import time
from datetime import datetime, timedelta
from pprint import pprint

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import json
import traceback

from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from ..libv2.api_desktops_common import ApiDesktopsCommon
from .flask_rethink import RDB
from .log import log

db = RDB(app)
db.init_app(app)
common = ApiDesktopsCommon()

import threading

from flask import request
from flask_socketio import (
    SocketIO,
    close_room,
    disconnect,
    emit,
    join_room,
    leave_room,
    rooms,
    send,
)

from .. import socketio
from .api_cards import ApiCards

api_cards = ApiCards()

threads = {}

from flask import Flask, _request_ctx_stack, jsonify, request

from ..auth.tokens import Error, get_token_payload
from .api_exceptions import Error
from .helpers import _parse_deployment_desktop, _parse_desktop

# from flask_cors import cross_origin


## Domains Threading
class DomainsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        last_deployment = None
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
                                "options",
                                {"create_dict": {"hardware": ["interfaces", "videos"]}},
                                "kind",
                                "tag",
                                "progress",
                                "jumperurl",
                            ]
                        )
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break

                        if c["new_val"] == None:
                            # Delete
                            if not c["old_val"]["id"].startswith("_"):
                                continue
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
                            if not c["new_val"]["id"].startswith("_"):
                                continue
                            if c["new_val"]["status"] not in [
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
                            ]:
                                continue

                            if c["new_val"]["kind"] != "desktop":
                                item = "template"
                            else:
                                item = "desktop"

                            if c["old_val"] == None:
                                # New
                                event = "add"
                            else:
                                # Update
                                event = "update"
                            data = c["new_val"]

                        socketio.emit(
                            item + "_" + event,
                            json.dumps(
                                data if item != "desktop" else _parse_desktop(data)
                            ),
                            namespace="/userspace",
                            room=item + "s_" + data["user"],
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
                                    room=item + "s_" + data["user"],
                                )

                        ## Tagged desktops to advanced users
                        if data["kind"] == "desktop" and data.get("tag", False):
                            deployment_id = data.get("tag")
                            try:
                                deployment = (
                                    r.table("deployments")
                                    .get(deployment_id)
                                    .pluck("id", "name", "user")
                                    .merge(
                                        lambda d: {
                                            "totalDesktops": r.table("domains")
                                            .get_all(d["id"], index="tag")
                                            .count(),
                                            "startedDesktops": r.table("domains")
                                            .get_all(d["id"], index="tag")
                                            .filter({"status": "Started"})
                                            .count(),
                                        }
                                    )
                                    .run(db.conn)
                                )

                                data = _parse_deployment_desktop(
                                    data, deployment["user"]
                                )
                                data.pop("name")
                                data.pop("description")
                                socketio.emit(
                                    "deploymentdesktop_" + event,
                                    json.dumps(data),
                                    namespace="/userspace",
                                    room="deploymentdesktops_" + deployment_id,
                                )

                                ## And then update deployments to user owner (if the deployment still exists)
                                if last_deployment == deployment:
                                    continue
                                else:
                                    last_deployment = deployment
                                socketio.emit(
                                    "deployment_update",
                                    json.dumps(deployment),
                                    namespace="/userspace",
                                    room="deployments_" + deployment["user"],
                                )
                            except:
                                log.debug(traceback.format_exc())

            except ReqlDriverError:
                print("DomainsThread: Rethink db connection lost!")
                log.error("DomainsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("DomainsThread internal error: restarting")
                log.error("DomainsThread internal error: restarting")
                log.error(traceback.format_exc())
                time.sleep(2)

        print("DomainsThread ENDED!!!!!!!")
        log.error("DomainsThread ENDED!!!!!!!")


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
    try:
        payload = get_token_payload(request.args.get("jwt"))

        if payload.get("desktop_id"):
            try:
                with app.app_context():
                    list(
                        r.table("domains").get(payload.get("desktop_id")).run(db.conn)
                    )[0]
            except:
                raise Error(
                    "not_found", "WS jumperurl token not found", traceback.format_exc()
                )
            join_room(payload.get("desktop_id"))
            log.debug(
                "Websocket direct viewer joined room: " + payload.get("desktop_id")
            )
        else:
            room = request.args.get("room")
            ## Rooms: desktop, deployment, deploymentdesktop
            if room == "deploymentdesktops":
                with app.app_context():
                    if (
                        r.table("deployments")
                        .get(request.args.get("deploymentId"))
                        .run(db.conn)["user"]
                        != payload["user_id"]
                    ):
                        raise
                deployment_id = request.args.get("deploymentId")
                join_room("deploymentdesktops_" + deployment_id)
            else:
                join_room(room + "_" + payload["user_id"])
            log.debug("User " + payload["user_id"] + " joined room: " + room)
    except:
        log.debug("Failed attempt to connect so socketio: " + traceback.format_exc())


@socketio.on("disconnect", namespace="/userspace")
def socketio_domains_disconnect():
    try:
        payload = get_token_payload(request.args.get("jwt"))
        if payload.get("desktop_id"):
            leave_room(payload.get("desktop_id"))
        else:
            for room in ["desktops", "deployments", "deployment_deskstop"]:
                leave_room(room + "_" + payload["user_id"])
    except:
        log.debug(traceback.format_exc())
