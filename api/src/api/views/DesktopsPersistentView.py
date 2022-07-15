# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from flask import request
from rethinkdb import RethinkDB

r = RethinkDB()

from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_hypervisors import get_hypervisors

desktops = ApiDesktopsPersistent()

from ..libv2.api_cards import ApiCards

api_cards = ApiCards()

from ..libv2.validators import _validate_item
from .decorators import allowedTemplateId, has_token, is_admin, ownsDomainId


@app.route("/api/v3/desktop/start/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_start(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    user_id = desktops.UserDesktop(desktop_id)
    quotas.DesktopStart(user_id)

    # So now we have checked if desktop exists and if we can create and/or start it
    return (
        json.dumps({"id": desktops.Start(desktop_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/start", methods=["PUT"])
@has_token
def api_v3_desktops_start(payload):
    try:
        data = request.get_json(force=True)
        desktops_ids = data["desktops_ids"]
    except:
        Error(
            "bad_request",
            "DesktopS start incorrect body data",
            traceback.format_exc(),
        )

    for desktop_id in desktops_ids:
        ownsDomainId(payload, desktop_id)
        user_id = desktops.UserDesktop(desktop_id)
        quotas.DesktopStart(user_id)

    # So now we have checked if desktop exists and if we can create and/or start it
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/stop/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_stop(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    user_id = desktops.UserDesktop(desktop_id)

    return (
        json.dumps({"id": desktops.Stop(desktop_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/stop", methods=["PUT"])
@has_token
def api_v3_desktops_stop(payload, desktop_id):
    try:
        data = request.get_json(force=True)
        desktops_ids = data["desktops_ids"]
    except:
        Error(
            "bad_request",
            "DesktopS start incorrect body data",
            traceback.format_exc(),
        )
    for desktop_id in desktops_ids:
        ownsDomainId(payload, desktop_id)
        user_id = desktops.UserDesktop(desktop_id)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/persistent_desktop", methods=["POST"])
@has_token
def api_v3_persistent_desktop_new(payload):
    try:
        data = request.get_json(force=True)
    except:
        Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
        )

    data = _validate_item("desktop_from_template", data)
    allowedTemplateId(payload, data["template_id"])
    quotas.DesktopCreate(payload["user_id"])

    desktop_id = desktops.NewFromTemplate(
        desktop_name=data["name"],
        desktop_description=data["description"],
        template_id=data["template_id"],
        payload=payload,
    )
    return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/desktop/from/media", methods=["POST"])
@has_token
def api_v3_desktop_from_media(payload):
    try:
        data = request.get_json(force=True)
    except:
        Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
        )
    data["user_id"] = payload["user_id"]
    data = _validate_item("desktop_from_media", data)
    quotas.DesktopCreate(payload["user_id"])

    desktop_id = desktops.NewFromMedia(payload, data)
    return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/desktop/<desktop_id>", methods=["PUT"])
@has_token
def api_v3_desktop_edit(payload, desktop_id):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop edit incorrect body data",
            traceback.format_exc(),
        )
    data["id"] = desktop_id
    _validate_item("desktop", data)
    ownsDomainId(payload, desktop_id)

    ## Server value
    if data.get("server", None) != None:
        data = {**data, **{"create_dict": {"server": data.get("server")}}}

    ## Pop image from data if exists and process
    if data.get("image"):
        image_data = data.pop("image")

        if not image_data.get("file"):
            img_uuid = api_cards.update(
                desktop_id, image_data["id"], image_data["type"]
            )
            card = api_cards.get_card(img_uuid, image_data["type"])
            return json.dumps(card), 200, {"Content-Type": "application/json"}
        else:
            img_uuid = api_cards.upload(desktop_id, image_data)
            card = api_cards.get_card(img_uuid, image_data["type"])
            return json.dumps(card), 200, {"Content-Type": "application/json"}

    desktops.Update(desktop_id, data)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/jumperurl/<desktop_id>", methods=["GET"])
@has_token
def api_v3_admin_viewer(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    data = desktops.JumperUrl(desktop_id)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/jumperurl_reset/<desktop_id>", methods=["PUT"])
@has_token
def admin_jumperurl_reset(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    try:
        data = request.get_json()
    except:
        raise Error("bad_request", "Bad body data", traceback.format_exc())
    response = desktops.JumperUrlReset(desktop_id, disabled=data.get("disabled"))
    return (
        json.dumps(response),
        200,
        {"Content-Type": "application/json"},
    )
