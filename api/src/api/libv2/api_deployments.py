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
import logging
import traceback

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .helpers import _parse_deployment_desktop


class ApiDeployments:
    def __init__(self):
        None

    def List(self, user_id):
        with app.app_context():
            deployments = list(
                r.table("deployments")
                .get_all(user_id, index="user")
                .pluck("id", "name")
                .merge(
                    lambda deployment: {
                        "totalDesktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .count(),
                        "startedDesktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .filter({"status": "Started"})
                        .count(),
                    }
                )
                .run(db.conn)
            )
        return deployments

    def Get(self, user_id, deployment_id):
        with app.app_context():
            deployment = (
                r.table("deployments")
                .get(deployment_id)
                .without("create_dict")
                .run(db.conn)
            )
            if user_id != deployment["user"]:
                raise
            desktops = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck(
                    "id",
                    "user",
                    "name",
                    "description",
                    "status",
                    "icon",
                    "os",
                    "image",
                    "persistent",
                    "parents",
                    "create_dict",
                    "viewer",
                    "options",
                )
                .run(db.conn)
            )

        parsed_desktops = []
        for desktop in desktops:
            tmp_desktop = _parse_deployment_desktop(desktop)
            desktop_name = tmp_desktop.pop("name")
            desktop_description = tmp_desktop.pop("description")
            parsed_desktops.append(tmp_desktop)

        return {
            "id": deployment["id"],
            "name": deployment["name"],
            "desktop_name": desktop_name,
            "description": desktop_description,
            "desktops": parsed_desktops,
        }
