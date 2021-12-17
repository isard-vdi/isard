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

from flask import Response, redirect, request, url_for

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()


@app.route("/api/v3/direct/<token>", methods=["GET"])
def api_v3_viewer(token):
    try:
        viewers = common.DesktopViewerFromToken(token)
        return (
            json.dumps(
                {
                    "vmName": viewers["vmName"],
                    "vmDescription": viewers["vmDescription"],
                    "viewers": viewers,
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )
    except DesktopNotFound:
        log.error("Jumper viewer desktop not found")
        return (
            json.dumps(
                {
                    "error": "desktop_not_found",
                    "msg": "Jumper viewer desktop not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotStarted:
        log.error("Jumper viewer desktop not started")
        return (
            json.dumps(
                {
                    "error": "desktop_not_started",
                    "msg": "Jumper viewer desktop not started",
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
    except DesktopActionTimeout:
        log.error("Jumper viewer desktop start timeout.")
        return (
            json.dumps(
                {
                    "error": "desktop_start_timeout",
                    "msg": "Jumper viewer desktop start timeout",
                }
            ),
            408,
            {"Content-Type": "application/json"},
        )
    except:
        log.error("Jumper viewer general exception: " + traceback.format_exc())
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Jumper viewer general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
    return (
        json.dumps({"error": "bad_request", "msg": "Incorrect access. exception: "}),
        400,
        {"Content-Type": "application/json"},
    )
