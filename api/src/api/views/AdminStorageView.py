# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_storage import (
    delete_storage,
    get_disk_tree,
    get_disks,
    get_media_domains,
    get_status,
    get_storage_domains,
)
from ..libv2.helpers import get_user_data
from .decorators import is_admin_or_manager, ownsMediaId, ownsStorageId


@app.route("/api/v3/storage/status", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage_status(payload):
    return (
        json.dumps(
            get_status(
                payload["category_id"] if payload["role_id"] == "manager" else None
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage", methods=["GET"])
@app.route("/api/v3/admin/storage/<status>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage(payload, status=None):
    if status == "delete_pending":
        disks = get_disks(
            status=status,
            last_domain_attached=True,
            category_id=(
                payload["category_id"] if payload["role_id"] == "manager" else None
            ),
        )
    else:
        disks = get_disks(
            status=status,
            category_id=(
                payload["category_id"] if payload["role_id"] == "manager" else None
            ),
        )
    return (
        json.dumps(disks),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/domains/<path:storage_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage_domains(payload, storage_id):
    ownsStorageId(payload, storage_id)
    return (
        json.dumps(get_storage_domains(storage_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/media/domains/<path:storage_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_media_domains(payload, storage_id):
    ownsMediaId(payload, storage_id)
    return (
        json.dumps(get_media_domains(storage_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/tree_list", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage_disk_tree(payload):
    return (
        json.dumps(get_disk_tree()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/<storage_id>", methods=["DELETE"])
@is_admin_or_manager
def api_v3_admin_storage_delete(payload, storage_id):
    return (
        json.dumps(delete_storage(storage_id)),
        200,
        {"Content-Type": "application/json"},
    )
