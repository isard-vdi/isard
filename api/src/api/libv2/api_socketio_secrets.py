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
import traceback

from rethinkdb.errors import ReqlDriverError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import threading

threads = {}


class SecretsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("secrets").changes(include_initial=True).run(db.conn)
                    ):
                        if self.stop == True:
                            break

                        if not c.get("old_val", False):
                            # Its initial loading to app.ram
                            app.ram["secrets"][c["new_val"]["id"]] = c["new_val"]
                            # Continue if we don't want initial to be passed to clients
                            continue

                        if c["new_val"] == None:
                            del app.ram["secrets"][c["old_val"]["id"]]
                        else:
                            app.ram["secrets"][c["new_val"]["id"]] = c["new_val"]

            except ReqlDriverError:
                print("SecretsThread: Rethink db connection lost!")
                app.logger.error("SecretsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("SecretsThread internal error: restarting")
                app.logger.error("SecretsThread internal error: restarting")
                app.logger.error(traceback.format_exc())
                time.sleep(2)

        print("SecretsThread ENDED!!!!!!!")
        app.logger.error("SecretsThread ENDED!!!!!!!")


def start_secrets_thread():
    global threads
    if "secrets" not in threads:
        threads["secrets"] = None
    if threads["secrets"] == None:
        threads["secrets"] = SecretsThread()
        threads["secrets"].daemon = True
        threads["secrets"].start()
        app.logger.info("SecretsThread Started")
