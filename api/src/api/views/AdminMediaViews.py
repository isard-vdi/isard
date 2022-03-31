import json
import logging as log
import os
import time
import traceback

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import admin_table_insert
from ..libv2.api_exceptions import Error
from ..libv2.apiv2_exc import *
from ..libv2.validators import _validate_item
from .decorators import is_admin_or_manager


# Add media
@app.route("/api/v3/admin/media", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_media_insert(payload):
    try:
        data = request.get_json()
    except Exception as e:
        raise Error("bad_request", "Unable to parse body data.", traceback.format_exc())
    log.error(payload)

    data["user"] = payload["user_id"]
    data["username"] = payload["user_id"].split("-")[3]
    data["category"] = payload["category_id"]
    data["group"] = payload["group_id"]
    data["url-web"] = data["url"]
    data["accessed"] = time.time()

    data = _validate_item("media", data)

    urlpath = (
        data["category"]
        + "/"
        + data["group"].split("-")[1]
        + "/"
        + payload["provider"]
        + "/"
        + data["user"].split("-")[2]
        + "-"
        + data["user"].split("-")[3]
        + "/"
        + data["name"].replace(" ", "_")
    )
    data["path"] = urlpath

    admin_table_insert("media", data)

    return json.dumps(data), 200, {"Content-Type": "application/json"}
