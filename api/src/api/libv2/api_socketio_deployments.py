#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

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
from ..libv2.deployments.api_deployments import get

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
                            deployment = get(c["new_val"]["id"], False)
                        else:
                            event = "update"
                            user = c["new_val"]["user"]
                            deployment = get(c["new_val"]["id"], False)
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
                print("DeploymentsThread internal error: restarting")
                log.error("DeploymentsThread internal error: restarting")
                log.error(traceback.format_exc())
                time.sleep(0.5)

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
