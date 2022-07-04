# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import json
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import jsonify, request

from api import app

from ..libv2.api_downloads import Downloads
from ..libv2.api_exceptions import Error
from ..libv2.api_users import ApiUsers, check_category_domain
from ..libv2.log import log
from ..libv2.quotas import Quotas
from .decorators import is_admin

quotas = Quotas()
users = ApiUsers()
downloads = Downloads()

"""
ADMIN/MANAGER jwt endpoints
"""


@app.route("/api/v3/admin/downloads/<kind>", methods=["GET"])
@is_admin
def api_v3_admin_downloads_desktops(payload, kind):
    return (
        json.dumps(downloads.getNewKind(kind, payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/downloads/desktop/<desktop_id>", methods=["POST"])
@is_admin
def api_v3_admin_downloads_desktops_download(desktop_id, payload):
    Downloads().download_desktop(desktop_id, payload["user_id"])
    return json.dumps({}), 200, {"Content-Type": "application/json"}
