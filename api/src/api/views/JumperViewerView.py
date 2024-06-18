# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os

from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.quotas import Quotas
from .decorators import maintenance

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent

common = ApiDesktopsCommon()
desktops = ApiDesktopsPersistent()


@app.route("/api/v3/direct/<token>", methods=["GET"])
def api_v3_viewer(token):
    maintenance()
    viewers = common.DesktopViewerFromToken(token, request=request)
    if not viewers:
        return
    vmState = viewers.pop("vmState", None)
    return (
        json.dumps(
            {
                "desktopId": viewers.pop("desktopId", None),
                "jwt": viewers.pop("jwt", None),
                "vmName": viewers.pop("vmName", None),
                "vmDescription": viewers.pop("vmDescription", None),
                "vmState": vmState,
                "scheduled": viewers.pop("scheduled", None),
                "viewers": viewers,
                "needs_booking": viewers.pop("needs_booking", False),
                "next_booking_start": viewers.pop("next_booking_start", None),
                "next_booking_end": viewers.pop("next_booking_end", None),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/direct/<token>/reset", methods=["PUT"])
def api_v3_desktop_reset(token):
    return (
        json.dumps({"id": desktops.Reset(token, request=request)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/direct/docs", methods=["GET"])
def api_v3_viewer_docs():
    return (
        json.dumps(
            {
                "viewers_documentation_url": os.environ.get(
                    "FRONTEND_VIEWERS_DOCS_URI",
                    "https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/",
                )
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )
