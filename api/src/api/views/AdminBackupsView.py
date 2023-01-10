# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from flask import Response, request

from api import app

from .._common.api_exceptions import Error
from .._common.tokens import get_token_payload
from ..libv2.api_admin import admin_table_insert, admin_table_update
from ..libv2.api_backups import (
    check_new_values,
    download_backup,
    info_backup_db,
    new_backup_db,
    remove_backup_db,
    restore_db,
    upload_backup,
)
from .decorators import is_admin

backup_data = {}
backup_db = []


@app.route("/api/v3/backup", methods=["POST"])
@is_admin
def admin_backup(payload):
    new_backup_db()
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/restore/<backup_id>", methods=["PUT"])
@is_admin
def admin_restore(payload, backup_id):
    restore_db(backup_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/restore/table/<table>", methods=["PUT"])
@is_admin
def admin_restore_table(payload, table):
    data = request.get_json(force=True)["data"]
    insert = data.pop("new_backup_data", None)
    if insert:
        admin_table_insert(table, data)
    else:
        admin_table_update(table, data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/<backup_id>", methods=["DELETE"])
@is_admin
def admin_backup_remove(payload, backup_id):
    remove_backup_db(backup_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/<backup_id>", methods=["GET"])
@is_admin
def admin_backup_info(payload, backup_id):
    global backup_data, backup_db
    backup_data, backup_db = info_backup_db(backup_id)
    return json.dumps(backup_data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/table/<table_id>", methods=["GET"])
@is_admin
def admin_backup_detailinfo(payload, table_id):
    global backup_data, backup_db
    new_db = check_new_values(table_id, backup_db[table_id])
    return json.dumps(new_db), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/backup/download/<backup_id>", methods=["GET"])
def admin_backup_download(backup_id):
    payload = get_token_payload(request.args.get("jwt"))
    if payload["role_id"] == "admin":
        filedir, filename, data = download_backup(backup_id)
        return Response(
            data,
            mimetype="application/x-gzip",
            headers={"Content-Disposition": "attachment;filename=" + filename},
        )
    else:
        raise Error(
            "forbidden", "Not enough rights to dowload a backup", traceback.format_exc()
        )


@app.route("/api/v3/backup/upload", methods=["POST"])
@is_admin
def admin_backup_upload(payload):
    for f in request.files:
        upload_backup(request.files[f])
    return json.dumps({}), 200, {"Content-Type": "application/json"}
