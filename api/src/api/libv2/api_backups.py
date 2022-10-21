#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import pickle
import tarfile
import time
from datetime import datetime

from rethinkdb import RethinkDB
from werkzeug.utils import secure_filename

from api import app

from .._common.api_exceptions import Error

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .._common.api_exceptions import Error
from ..auth.authentication import *


def remove_backup_db(id):
    with app.app_context():
        dict = r.table("backups").get(id).run(db.conn)
    path = dict["path"]
    try:
        os.remove(path + id + ".tar.gz")
    except OSError:
        pass
    with app.app_context():
        r.table("backups").get(id).delete().run(db.conn)


def new_backup_db():
    id = "isard_backup_" + datetime.now().strftime("%Y%m%d-%H%M%S")
    path = "./backups/"
    os.makedirs(path, exist_ok=True)
    with app.app_context():
        dict = {
            "id": id,
            "filename": id + ".tar.gz",
            "path": path,
            "description": "",
            "when": int(time.time()),
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
        r.table("backups").get(id).update({"status": "Dumping to file"}).run(db.conn)
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
        r.table("backups").get(id).update({"status": "Finished creating"}).run(db.conn)


def recreate_table(tbl_data):
    if not r.table_list().contains(tbl_data["name"]).run(db.conn):
        log.info("Restoring table {}".format(k))
        r.table_create(tbl_data["name"], primary_key=tbl_data["primary_key"]).run(
            db.conn
        )
        for idx in tbl_data["indexes"]:
            r.table(tbl_data["name"]).index_create(idx).run(db.conn)
            r.table(tbl_data["name"]).index_wait(idx).run(db.conn)
            log.info("Created index: {}".format(idx))


def restore_db(id):
    with app.app_context():
        dict = r.table("backups").get(id).run(db.conn)
        r.table("backups").get(id).update({"status": "Uncompressing backup"}).run(
            db.conn
        )
    path = dict["path"]
    with tarfile.open(path + id + ".tar.gz", "r:gz") as tar:
        tar.extractall(path)
        tar.close()
    with app.app_context():
        r.table("backups").get(id).update({"status": "Loading data.."}).run(db.conn)
    with open(path + id + ".rethink", "rb") as tbl_data_file:
        tbl_data = pickle.load(tbl_data_file)
    with open(path + id + ".json", "rb") as isard_db_file:
        isard_db = pickle.load(isard_db_file)
    for k, v in isard_db.items():
        with app.app_context():
            try:
                recreate_table(tbl_data[k])
            except Exception as e:
                pass
            if not r.table_list().contains(k).run(db.conn):
                log.error(
                    "Table {} not found, should have been created on IsardVDI startup.".format(
                        k
                    )
                )
                continue
            else:
                log.info("Restoring table {}".format(k))
                with app.app_context():
                    r.table("backups").get(id).update(
                        {"status": "Updating table: " + k}
                    ).run(db.conn)
                # Avoid updating admin user!
                if k == "users":
                    v[:] = [u for u in v if u.get("id") != "admin"]
                log.info(r.table(k).insert(v, conflict="update").run(db.conn))
    with app.app_context():
        r.table("backups").get(id).update({"status": "Finished restoring"}).run(db.conn)
    try:
        os.remove(path + id + ".json")
        os.remove(path + id + ".rethink")
    except OSError as e:
        log.error(e)
        pass


def download_backup(id):
    with app.app_context():
        dict = r.table("backups").get(id).run(db.conn)
    with open(dict["path"] + dict["filename"], "rb") as isard_db_file:
        return dict["path"], dict["filename"], isard_db_file.read()


def info_backup_db(id):
    with app.app_context():
        dict = r.table("backups").get(id).run(db.conn)
    path = dict["path"]
    with tarfile.open(path + id + ".tar.gz", "r:gz") as tar:
        tar.extractall(path)
        tar.close()
    with open(path + id + ".rethink", "rb") as tbl_data_file:
        tbl_data = pickle.load(tbl_data_file)
    with open(path + id + ".json", "rb") as isard_db_file:
        isard_db = pickle.load(isard_db_file)
    i = 0
    for sch in isard_db["scheduler_jobs"]:
        isard_db["scheduler_jobs"][i].pop("job_state", None)
        i = i + 1
    try:
        os.remove(path + id + ".json")
        os.remove(path + id + ".rethink")
    except OSError as e:
        log.error(e)
        pass
    return tbl_data, isard_db


def check_new_values(table, new_data):
    backup = new_data
    dbb = list(r.table(table).run(db.conn))
    result = []
    for b in backup:
        found = False
        for d in dbb:
            if d["id"] == b["id"]:
                found = True
                b["new_backup_data"] = False
                result.append(b)
                break
        if not found:
            b["new_backup_data"] = True
            result.append(b)
    return result


def upload_backup(handler):
    path = "./backups/"
    id = handler.filename.split(".tar.gz")[0]
    filename = secure_filename(handler.filename)
    handler.save(os.path.join(path + filename))

    with tarfile.open(path + handler.filename, "r:gz") as tar:
        tar.extractall(path)
        tar.close()
    with open(path + id + ".rethink", "rb") as isard_rethink_file:
        isard_rethink = pickle.load(isard_rethink_file)
    with app.app_context():
        log.info(
            r.table("backups").insert(isard_rethink, conflict="update").run(db.conn)
        )
    with app.app_context():
        r.table("backups").get(id).update({"status": "Finished uploading"}).run(db.conn)
    try:
        os.remove(path + id + ".json")
        os.remove(path + id + ".rethink")
    except OSError as e:
        log.error(e)
        pass


def remove_backup_db(id):
    with app.app_context():
        dict = r.table("backups").get(id).run(db.conn)
    path = dict["path"]
    try:
        os.remove(path + id + ".tar.gz")
    except OSError:
        pass
    with app.app_context():
        r.table("backups").get(id).delete().run(db.conn)
