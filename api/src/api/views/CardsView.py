#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

from api import app

from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_cards import ApiCards

api_cards = ApiCards()

from .._common.api_exceptions import Error
from .decorators import has_token, is_admin


@app.route("/api/v3/images/desktops", methods=["GET"])
@app.route("/api/v3/images/desktops/<image_type>", methods=["GET"])
@has_token
def api_v3_images_desktops(payload, image_type=None):
    try:
        domain_id = request.args.get("desktop_id")
    except:
        raise Error(
            "bad_request",
            "Desktop images bad request",
            traceback.format_exc(),
        )

    if not image_type:
        images = api_cards.get_stock_cards() + api_cards.get_user_cards(
            payload["user_id"],
            domain_id,
        )
    elif image_type == "stock":
        images = api_cards.get_stock_cards()
    elif image_type == "user":
        images = api_cards.get_user_cards(payload["user_id"], domain_id)
    else:
        raise
    return (
        json.dumps(images),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/images/desktops/stock/default/<domain_id>", methods=["GET"])
@has_token
def api_v3_images_desktops_stock_default(payload, domain_id):
    return (
        json.dumps(api_cards.get_domain_stock_card(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/images/desktops/user/default/<domain_id>", methods=["GET"])
@has_token
def api_v3_images_desktops_user_default(payload, domain_id):
    return (
        json.dumps(api_cards.get_domain_user_card(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/images/desktops/generate", methods=["POST"])
@is_admin
def api_v3_images_desktops_generate(payload):
    try:
        domain_id = request.form.get("desktop_id", type=str)
        domain_name = request.form.get("desktop_name", type=str)
    except:
        Error(
            "bad_request",
            "Generate desktops images bad body data",
            traceback.format_exc(),
        )

    return (
        json.dumps(api_cards.generate_default_card(domain_id, domain_name)),
        200,
        {"Content-Type": "application/json"},
    )
