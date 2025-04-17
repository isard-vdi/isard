# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import html
import json
import os

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_users import ApiUsers
from ..libv2.caches import get_config

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


@cached(cache=TTLCache(maxsize=1, ttl=20))
@app.route("/api/v3/categories", methods=["GET"])
def api_v3_categories():
    return (
        json.dumps(users.CategoriesFrontendGet()),
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
def api_v3_login_config():
    login_config = get_config().get("login", {})
    for key in ["notification_cover", "notification_form"]:
        if key in login_config:
            for field in ["description", "title", "text"]:
                if (
                    "button" in login_config[key]
                    and field in login_config[key]["button"]
                    and login_config[key]["button"][field] is not None
                ):
                    login_config[key]["button"][field] = html.unescape(
                        login_config[key]["button"][field]
                    )
                if field in login_config[key] and login_config[key][field] is not None:
                    login_config[key][field] = html.unescape(login_config[key][field])
    return (
        json.dumps(login_config),
        200,
        {"Content-Type": "application/json"},
    )
