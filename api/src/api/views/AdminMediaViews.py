import json
import logging as log
import os
import time
import traceback

from flask import request
from rethinkdb import RethinkDB

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import admin_table_insert
from ..libv2.api_exceptions import Error
from ..libv2.flask_rethink import RDB
from ..libv2.validators import _validate_item
from .decorators import is_admin_or_manager

r = RethinkDB()
db = RDB(app)
db.init_app(app)


# Add media
@app.route("/api/v3/admin/media", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_media_insert(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.traceback.format_exc(),
        )

    with app.app_context():
        username = r.table("users").get(payload["user_id"])["username"].run(db.conn)
        uid = r.table("users").get(payload["user_id"])["uid"]
        if username == None:
            raise Error("not_found", "User not found", traceback.traceback.format_exc())
        group = r.table("groups").get(payload["group_id"])["uid"].run(db.conn)
        if group == None:
            raise Error(
                "not_found", "Group not found", traceback.traceback.format_exc()
            )

    data["user"] = payload["user_id"]
    data["username"] = username
    data["category"] = payload["category_id"]
    data["group"] = payload["group_id"]
    data["url-web"] = data["url"]
    data["accessed"] = time.time()

    data = _validate_item("media", data)

    urlpath = (
        data["category"]
        + "/"
        + group
        + "/"
        + payload["provider"]
        + "/"
        + uid
        + "-"
        + username
        + "/"
        + data["name"].replace(" ", "_")
    )
    data["path"] = urlpath

    admin_table_insert("media", data)

    return json.dumps({}), 200, {"Content-Type": "application/json"}
