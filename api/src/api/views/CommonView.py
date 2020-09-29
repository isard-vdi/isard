# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from api import app
import logging as log
import traceback

from uuid import uuid4
import time, json
import sys, os
from flask import request
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *

from flask import (
    render_template,
    Response,
    request,
    redirect,
    url_for,
    send_file,
    send_from_directory,
)

# from ..libv2.telegram import tsend
def tsend(txt):
    None


from ..libv2.carbon import Carbon

carbon = Carbon()

from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()


@app.route("/api/v2/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
def api_v2_desktop_viewer(desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"ContentType": "application/json"},
        )

    try:
        viewer = common.DesktopViewer(desktop_id, protocol)
        return json.dumps({"viewer": viewer}), 200, {"ContentType": "application/json"}
    except DesktopNotFound:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", desktop not found"
        )
        return (
            json.dumps({"code": 1, "msg": "Desktop viewer id not found"}),
            404,
            {"ContentType": "application/json"},
        )
    except DesktopNotStarted:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", desktop not started"
        )
        return (
            json.dumps({"code": 2, "msg": "Desktop viewer is not started"}),
            404,
            {"ContentType": "application/json"},
        )
    except NotAllowed:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer access not allowed"
        )
        return (
            json.dumps({"code": 3, "msg": "Desktop viewer id not owned by user"}),
            404,
            {"ContentType": "application/json"},
        )
    except ViewerProtocolNotFound:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer protocol not found"
        )
        return (
            json.dumps({"code": 4, "msg": "Desktop viewer protocol not found"}),
            404,
            {"ContentType": "application/json"},
        )
    except ViewerProtocolNotImplemented:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer protocol not implemented"
        )
        return (
            json.dumps({"code": 5, "msg": "Desktop viewer protocol not implemented"}),
            404,
            {"ContentType": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps({"code": 9, "msg": "DesktopViewer general exception: " + error}),
            401,
            {"ContentType": "application/json"},
        )
