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

from .flask_rethink import RDB
from .log import log

db = RDB(app)
db.init_app(app)

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
        for room in ["desktops", "deployments", "deployment_deskstop"]:
            leave_room(room + "_" + payload["user_id"])
    except:
        pass
