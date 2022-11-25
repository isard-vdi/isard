#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error

r = RethinkDB()
import json
import logging as log
import traceback

from rethinkdb.errors import ReqlDriverError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import threading

from .. import socketio
from .helpers import _parse_deployment_booking

threads = {}


class DeploymentsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("deployments")
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            event = "delete"
                            user = c["old_val"]["user"]
                            deployment = {"id": c["old_val"]["id"]}
                        elif c["old_val"] == None:
                            event = "add"
                            user = c["new_val"]["user"]
                            deployment = {
                                "id": c["new_val"]["id"],
                                "name": c["new_val"]["name"],
                                "user": user,
                                "totalDesktops": r.table("domains")
                                .get_all(c["new_val"]["id"], index="tag")
                                .count()
                                .run(db.conn),
                                "startedDesktops": 0,
                                "visible": c["new_val"]["create_dict"]["tag_visible"],
                                "desktop_name": c["new_val"]["create_dict"]["name"],
                            }
                        else:
                            event = "update"
                            user = c["new_val"]["user"]
                            deployment = {
                                "id": c["new_val"]["id"],
                                "name": c["new_val"]["name"],
                                "user": user,
                                "totalDesktops": r.table("domains")
                                .get_all(c["new_val"]["id"], index="tag")
                                .count()
                                .run(db.conn),
                                "startedDesktops": r.table("domains")
                                .get_all(c["new_val"]["id"], index="tag")
                                .filter({"status": "Started"})
                                .count()
                                .run(db.conn),
                                "visible": c["new_val"]["create_dict"]["tag_visible"],
                                "desktop_name": c["new_val"]["create_dict"]["name"],
                            }
                            deployment = {
                                **deployment,
                                **_parse_deployment_booking(deployment),
                            }
                            socketio.emit(
                                "deployment_update",
                                json.dumps(deployment),
                                namespace="/userspace",
                                room=user,
                            )

                        socketio.emit(
                            "deployments_" + event,
                            json.dumps(deployment),
                            namespace="/userspace",
                            room=user,
                        )

            except ReqlDriverError:
                print("DeploymentsThread: Rethink db connection lost!")
                log.error("DeploymentsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                raise Error(
                    "internal_server",
                    "Deployments websocket restart",
                    traceback.format_exc(),
                )
                time.sleep(0.1)

        print("DeploymentsThread ENDED!!!!!!!")
        log.error("DeploymentsThread ENDED!!!!!!!")


def start_deployments_thread():
    global threads
    if "deployments" not in threads:
        threads["deployments"] = None
    if threads["deployments"] == None:
        threads["deployments"] = DeploymentsThread()
        threads["deployments"].daemon = True
        threads["deployments"].start()
        log.info("DeploymentsThread Started")
