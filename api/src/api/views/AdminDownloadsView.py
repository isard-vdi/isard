# Copyright 2017 the Isard-vdi project
# License: AGPLv3

import json

from flask import request

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_admin import admin_table_delete, admin_table_insert, admin_table_update
from ..libv2.api_downloads import Downloads
from .decorators import is_admin

downloads = Downloads()


@app.route("/api/v3/admin/downloads/<kind>", methods=["GET"])
@is_admin
def api_v3_admin_downloads_desktops(payload, kind):
    return (
        json.dumps(downloads.getNewKind(kind, payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/downloads/register", methods=["POST"])
@is_admin
def admin_updates_register():
    if request.method == "POST":
        try:
            if not downloads.is_registered():
                downloads.register()
        except Exception as e:
            app.logger.error("Error registering client: " + str(e))
            # ~ return False
    if not downloads.is_conected():
        raise Error(
            "gateway_timeout",
            "There is a network or update server error at the moment. Try again later.",
        )
    registered = downloads.is_registered()
    if not registered:
        raise Error("precondition_required", "IsardVDI hasn't been registered yet.")
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/downloads/reload", methods=["POST"])
@is_admin
def admin_updates_reload():
    if request.method == "POST":
        downloads.reload_updates()
    if not downloads.is_conected():
        raise Error(
            "gateway_timeout",
            "There is a network or update server error at the moment. Try again later.",
        )
    registered = downloads.is_registered()
    if not registered:
        raise Error("precondition_required", "IsardVDI hasn't been registered yet.")
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/downloads/<action>/<kind>", methods=["POST"])
@app.route("/api/v3/admin/downloads/<action>/<kind>/<id>", methods=["POST"])
@is_admin
def admin_updates_actions(payload, action, kind, id=False):
    if request.method == "POST":
        if action == "download":
            if id:
                # Only one id
                d = downloads.getNewKindId(kind, payload["user_id"], id)
                if kind == "domains":
                    missing_resources = downloads.get_missing_resources(
                        d, payload["user_id"]
                    )
                    for k, v in missing_resources.items():
                        for resource in v:
                            try:
                                admin_table_insert(k, v)
                            except:
                                admin_table_update(k, v)
                if d:
                    if kind == "domains":
                        d = downloads.formatDomains([d], payload["user_id"])[0]
                    elif kind == "media":
                        d = downloads.formatMedias([d], payload["user_id"])[0]
                    try:
                        admin_table_insert(kind, d)
                    except:
                        admin_table_update(kind, d)
            else:
                # No id, do it will all
                data = downloads.getNewKind(kind, payload["user_id"])
                data = [d for d in data if d["new"] is True]
                if kind == "domains":
                    data = downloads.formatDomains(data, payload["user_id"])
                elif kind == "media":
                    data = downloads.formatMedias(data, payload["user_id"])
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
