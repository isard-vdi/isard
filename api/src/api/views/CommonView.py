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

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()

from .decorators import (
    allowedTemplateId,
    has_token,
    is_admin,
    ownsCategoryId,
    ownsDomainId,
    ownsUserId,
)


@app.route("/api/v3/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
@has_token
def api_v3_desktop_viewer(payload, desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    if not ownsDomainId(payload, desktop_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
    try:
        viewer = common.DesktopViewer(desktop_id, protocol, get_cookie=True)
        return json.dumps(viewer), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", desktop not found"
        )
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Desktop viewer: desktop id not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
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
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Desktop viewer: desktop is not started",
                }
            ),
            404,
            {"Content-Type": "application/json"},
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
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Desktop viewer: desktop id not owned by user",
                }
            ),
            404,
            {"Content-Type": "application/json"},
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
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Desktop viewer: viewer protocol not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
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
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Desktop viewer: viewer protocol not implemented",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopViewer general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop/<desktop_id>/viewers", methods=["GET"])
@has_token
def api_v2_desktop_viewers(payload, desktop_id=False, protocol=False):
    if not ownsDomainId(payload, desktop_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
    viewers = []
    for protocol in ["browser-vnc", "file-spice"]:
        try:
            viewer = common.DesktopViewer(desktop_id, protocol, get_cookie=True)
            viewers.append(viewer)
        except DesktopNotFound:
            log.error(
                "Viewer for desktop "
                + desktop_id
                + " with protocol "
                + protocol
                + ", desktop not found"
            )
            return (
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Desktop viewer: desktop id not found",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
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
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Desktop viewer: desktop is not started",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
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
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Desktop viewer: desktop id not owned by user",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
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
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Desktop viewer: viewer protocol not found",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
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
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Desktop viewer: viewer protocol not implemented",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
            )
        except Exception as e:
            error = traceback.format_exc()
            return (
                json.dumps(
                    {
                        "error": "generic_error",
                        "msg": "DesktopViewer general exception: " + error,
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )
    return json.dumps(viewers), 200, {"Content-Type": "application/json"}
