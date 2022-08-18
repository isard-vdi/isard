# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

from api import app

from ..libv2.api_exceptions import Error
from ..libv2.api_storage import get_disks, get_storage_domains
from ..libv2.helpers import get_user_data
from .decorators import is_admin_or_manager, ownsStorageId


@app.route("/api/v3/admin/storage", methods=["GET"])
@app.route("/api/v3/admin/storage/<status>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage(payload, status=None):
    disks = get_disks(status=status)
    if payload["role_id"] == "manager":
        disks = [d for d in disks if d["category"] == payload["category_id"]]
    return (
        json.dumps(disks),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/domains/<storage_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_storage_domains(payload, storage_id):
    ownsStorageId(payload, storage_id)
    return (
        json.dumps(get_storage_domains(storage_id)),
        200,
        {"Content-Type": "application/json"},
    )