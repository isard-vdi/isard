# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import html
import json
import os

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from flask import request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.category import Category
from isardvdi_common.configuration import Configuration

from api import app

from ..libv2.api_users import ApiUsers

users = ApiUsers()

with open("/version", "r") as file:
    version = file.read()


@cached(cache=TTLCache(maxsize=1, ttl=360))
@app.route("/api/v3", methods=["GET"])
def api_v3_test():
    return (
        json.dumps(
            {
                "name": "IsardVDI",
                "api_version": 3.1,
                "isardvdi_version": version,
                "usage": os.environ.get("USAGE"),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(
    cache=TTLCache(maxsize=10, ttl=20), key=lambda: hashkey(request.headers.get("Host"))
)
@app.route("/api/v3/categories", methods=["GET"])
def api_v3_categories():
    return (
        json.dumps(users.CategoriesFrontendGet(request.headers.get("Host"))),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=1, ttl=20))
@app.route("/api/v3/category/<custom_url>", methods=["GET"])
def api_v3_category(custom_url):
    return (
        json.dumps(users.category_get_by_custom_url(custom_url)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=1, ttl=20))
@app.route("/api/v3/category/<category_id>/custom_url", methods=["GET"])
def api_v3_category_custom_url(category_id):
    return (
        users.category_get_custom_login_url(category_id),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=1, ttl=20))
@app.route("/api/v3/login_config", methods=["GET"])
@app.route("/api/v3/login_config/<category_id>", methods=["GET"])
def api_v3_login_config(category_id=None):
    if category_id and Category.exists(category_id):
        login_config = Category(category_id).login_notification or {}
    else:
        login_config = Configuration.login or {}
    for key in ("notification_cover", "notification_form"):
        notification = login_config.get(key)
        if notification:
            for field in ("title", "description"):
                if field in notification and notification[field]:
                    notification[field] = html.unescape(notification[field])
            button = notification.get("button")
            if button:
                for field in ("text", "url"):
                    if field in button and button[field]:
                        button[field] = html.unescape(button[field])
    return (
        json.dumps(login_config),
        200,
        {"Content-Type": "application/json"},
    )
