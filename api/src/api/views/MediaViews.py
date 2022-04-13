import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import request

from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_media import ApiMedia

api_media = ApiMedia()

from .decorators import has_token


@app.route("/api/v3/media", methods=["GET"])
@has_token
def api_v3_admin_media(payload):
    try:
        medias = api_media.Get(payload)
        return json.dumps(medias), 200, {"Content-Type": "application/json"}
    # except MediaNotFound:
    #     log.error("User "+id+" not in database.")
    #     return json.dumps({"error": "undefined_error","msg":"UserDesktops: User not exists in database"}), 404, {'Content-Type': 'application/json'}
    except UserMediaError:
        log.error("Media listing failed.")
        return (
            json.dumps({"error": "undefined_error", "msg": "MediaGet: list error"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "MediaGet general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktops/media_list", methods=["POST"])
@has_token
def api_v3_desktops_media_list(payload):
    data = request.get_json(force=True)
    return (
        json.dumps(api_media.GetMediaList(data["pk"])),
        200,
        {"Content-Type": "application/json"},
    )
