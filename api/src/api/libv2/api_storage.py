#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3


from rethinkdb import RethinkDB

from api import app

from .api_exceptions import Error

r = RethinkDB()
import csv
import io
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .api_exceptions import Error
from .helpers import get_user_data
from .validators import _validate_item, _validate_table


def get_disks(user_id=None, status=None):
    query = r.table("storage")
    if user_id:
        query = query.get_all(user_id, index="user_id")
        if status:
            query = query.filter({"status": status})
    elif status:
        query = query.get_all(status, index="status")
    query = query.pluck(
        [
            "id",
            "type",
            "status",
            "directory_path",
            "parent",
            "user_id",
            "status_logs",
            {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
        ]
    )
    query = query.merge(
        lambda disk: {
            "user_name": r.table("users")
            .get(disk["user_id"])
            .default({"name": "[DELETED] " + disk["user_id"]})["name"],
            "category": r.table("users")
            .get(disk["user_id"])
            .default({"category": "[DELETED]"})["category"],
            "domains": r.table("domains")
            .get_all(disk["id"], index="storage_ids")
            .count(),
        }
    )
    with app.app_context():
        return list(query.run(db.conn))


def get_storage_domains(storage_id):
    with app.app_context():
        return list(
            r.table("domains")
            .get_all(storage_id, index="storage_ids")
            .pluck("id", "kind", "name")
            .run(db.conn)
        )


def get_media_domains(storage_id):
    with app.app_context():
        return list(
            r.table("domains")
            .get_all(storage_id, index="media_ids")
            .pluck("id", "kind", "name")
            .run(db.conn)
        )
