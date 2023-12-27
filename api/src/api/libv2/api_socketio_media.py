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

from .api_media import media_task_delete
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import threading

from .. import socketio

threads = {}


class MediaThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("media")
                        .get_all(
                            r.args(
                                [
                                    "Deleting",
                                    "deleted",
                                    "Downloaded",
                                    "DownloadFailed",
                                    "DownloadFailedInvalidFormat",
                                    "DownloadStarting",
                                    "Downloading",
                                    "Download",
                                    "DownloadAborting",
                                    "ResetDownloading",
                                ]
                            ),
                            index="status",
                        )
                        .changes(include_initial=False, squash=0.5)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None or c["new_val"]["status"] == "deleted":
                            data = c["old_val"]
                            event = "delete"
                        elif c["old_val"] == None:
                            data = c["new_val"]
                            event = "add"
                        else:
                            data = c["new_val"]
                            event = "update"
                            if (
                                c["old_val"]
                                and c["new_val"].get("status")
                                == "DownloadFailedInvalidFormat"
                            ):
                                media_task_delete(
                                    c["new_val"]["id"],
                                    c["new_val"]["user"],
                                    keep_status=True,
                                )

                        ## TODO: Users should receive not only their media updates, also the shared one's with them!
                        socketio.emit(
                            "media_" + event,
                            json.dumps(
                                {**data, "editable": True}
                            ),  # The owner can edit its data
                            namespace="/userspace",
                            room=data["user"],
                        )
                        socketio.emit(
                            "media_" + event,
                            json.dumps(data),
                            namespace="/administrators",
                            room=data["category"],
                        )
                        socketio.emit(
                            "media_" + event,
                            json.dumps(data),
                            namespace="/administrators",
                            room="admins",
                        )
            except ReqlDriverError:
                print("MediaThread: Rethink db connection lost!")
                log.error("MediaThread: Rethink db connection lost!")
                time.sleep(5)
            except Exception as e:
                print("MediaThread internal error: \n" + traceback.format_exc())
                log.error("MediaThread internal error: \n" + traceback.format_exc())


def start_media_thread():
    global threads
    if "media" not in threads:
        threads["media"] = None
    if threads["media"] == None:
        threads["media"] = MediaThread()
        threads["media"].daemon = True
        threads["media"].start()
        log.info("MediaThread Started")
