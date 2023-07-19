# Copyright 2017 the Isard-vdi project
# License: AGPLv3

import json

from flask import request

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_admin import admin_table_delete, admin_table_insert, admin_table_update
from ..libv2.api_downloads import (
    formatDomains,
    formatMedias,
    get_missing_resources,
    get_new_kind,
    get_new_kind_id,
    is_registered,
    register,
)
from .decorators import is_admin


@app.route("/api/v3/admin/downloads", methods=["GET"])
@is_admin
@is_registered
def api_v3_admin_downloads(payload):
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/downloads/<kind>", methods=["GET"])
@is_admin
@is_registered
def api_v3_admin_downloads_kind(payload, kind):
    return (
        json.dumps(get_new_kind(kind, payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/downloads/register", methods=["POST"])
@is_admin
def admin_downloads_register(payload):
    register()
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/downloads/<action>/<kind>", methods=["POST"])
@app.route("/api/v3/admin/downloads/<action>/<kind>/<id>", methods=["POST"])
@is_admin
@is_registered
def admin_downloads_actions(payload, action, kind, id=False):
    if request.method == "POST":
        if action == "download":
            if id:
                # Only one id
                d = get_new_kind_id(kind, payload["user_id"], id)
                if kind == "domains":
                    missing_resources = get_missing_resources(d, payload["user_id"])
                    for k, v in missing_resources.items():
                        for resource in v:
                            try:
                                admin_table_insert(k, v)
                            except:
                                admin_table_update(k, v)
                if d:
                    if kind == "domains":
                        d = formatDomains([d], payload["user_id"])[0]
                    elif kind == "media":
                        d = formatMedias([d], payload["user_id"])[0]
                    try:
                        admin_table_insert(kind, d)
                    except:
                        admin_table_update(kind, d)
            else:
                # No id, do it will all
                data = get_new_kind(kind, payload["user_id"])
                data = [d for d in data if d["new"] is True]
                if kind == "domains":
                    data = formatDomains(data, payload["user_id"])
                elif kind == "media":
                    data = formatMedias(data, payload["user_id"])
                for item in data:
                    try:
                        admin_table_insert(kind, item)
                    except:
                        admin_table_update(kind, item)
        if action == "abort":
            data = {"id": id, "status": "DownloadAborting"}
            admin_table_update(kind, data)
        if action == "delete":
            if kind == "domains" or kind == "media":
                data = {"id": id, "status": "Deleting"}
                admin_table_update(kind, data)
            else:
                admin_table_delete(kind, id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}
