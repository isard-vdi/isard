# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import queue
import random
import time

#!/usr/bin/env python
# coding=utf-8
from decimal import Decimal
from threading import Thread

import pytz
from flask import current_app
from rethinkdb import RethinkDB

from scheduler import app

r = RethinkDB()
import logging
import os
import pickle
import tarfile
import traceback

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from datetime import datetime, timedelta


class Actions:
    def stop_domains():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").update(
                {"status": "Stopping"}
            ).run(db.conn)

    def stop_domains_without_viewer():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").filter(
                {"viewer": {"client_since": False}}
            ).update({"status": "Stopping"}).run(db.conn)

    def stop_shutting_down_desktops():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Shutting-down", index="status")
                .pluck("id", "accessed")
                .run(db.conn)
            )
            t = time.time()
            for d in domains:
                if d["accessed"] + 1.9 * 60 < t:  # 2 minutes * 60 seconds
                    r.table("domains").get(d["id"]).update(
                        {"status": "Stopping", "accessed": time.time()}
                    ).run(db.conn)

    def check_ephimeral_status():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Started", index="status")
                .has_fields("ephimeral")
                .pluck("id", "ephimeral", "history_domain")
                .run(db.conn)
            )
            t = time.time()
            for d in domains:
                if (
                    d["history_domain"][0]["when"] + int(d["ephimeral"]["minutes"]) * 60
                    < t
                ):
                    r.table("domains").get(d["id"]).update(
                        {"status": d["ephimeral"]["action"]}
                    ).run(db.conn)

    def backup_database():
        id = "isard_backup_" + datetime.now().strftime("%Y%m%d-%H%M%S")
        path = "./backups/"
        os.makedirs(path, exist_ok=True)
        with app.app_context():
            dict = {
                "id": id,
                "filename": id + ".tar.gz",
                "path": path,
                "description": "",
                "when": time.time(),
                "data": {},
                "status": "Initializing",
                "version": r.table("config")
                .get(1)
                .pluck("version")
                .run(db.conn)["version"],
            }
        with app.app_context():
            r.table("backups").insert(dict).run(db.conn)
        skip_tables = [
            "backups",
            "disk_operations",
        ]
        isard_db = {}
        with app.app_context():
            r.table("backups").get(id).update({"status": "Loading tables"}).run(db.conn)
            for table in r.table_list().run(db.conn):
                if table not in skip_tables:
                    isard_db[table] = list(r.table(table).run(db.conn))
                    dict["data"][table] = r.table(table).info().run(db.conn)
                    r.table("backups").get(id).update(
                        {"data": {table: r.table(table).count().run(db.conn)}}
                    ).run(db.conn)
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
            r.table("backups").get(id).update({"status": "Dumping to file"}).run(
                db.conn
            )
        with open(path + id + ".rethink", "wb") as isard_rethink_file:
            pickle.dump(dict, isard_rethink_file)
        with open(path + id + ".json", "wb") as isard_db_file:
            pickle.dump(isard_db, isard_db_file)
        with app.app_context():
            r.table("backups").get(id).update({"status": "Compressing"}).run(db.conn)
        with tarfile.open(path + id + ".tar.gz", "w:gz") as tar:
            tar.add(path + id + ".json", arcname=os.path.basename(path + id + ".json"))
            tar.add(
                path + id + ".rethink", arcname=os.path.basename(path + id + ".rethink")
            )
            tar.close()
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError:
            pass
        with app.app_context():
            r.table("backups").get(id).update({"status": "Finished creating"}).run(
                db.conn
            )

    """
    BULK ACTIONS
    """

    def bulk_action(table, tbl_filter, tbl_update):
        with app.app_context():
            log.info(
                "BULK ACTION: Table {}, Filter {}, Update {}".format(
                    table, filter, update
                )
            )
            r.table(table).filter(filter).update(update).run(db.conn)
            r.table(table).filter({"status": "Unknown"}).update(
                {"status": "Stopping"}
            ).run(db.conn)
