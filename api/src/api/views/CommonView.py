# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import (
    Response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()

from .decorators import allowedTemplateId, has_token, is_admin, ownsDomainId


@app.route("/api/v3/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
@has_token
def api_v3_desktop_viewer(payload, desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        raise Error(
            "bad_request",
            "Desktop viewer incorrect body data",
            traceback.format_exc(),
        )

    ownsDomainId(payload, desktop_id)
    return (
        json.dumps(common.DesktopViewer(desktop_id, protocol, get_cookie=True)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/<desktop_id>/viewers", methods=["GET"])
@has_token
def api_v2_desktop_viewers(payload, desktop_id=False, protocol=False):
    ownsDomainId(payload, desktop_id)
    viewers = []
    for protocol in ["browser-vnc", "file-spice"]:
        viewer = common.DesktopViewer(desktop_id, protocol, get_cookie=True)
        viewers.append(viewer)
    return json.dumps(viewers), 200, {"Content-Type": "application/json"}
