# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import json
import os

from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_users import ApiUsers

users = ApiUsers()

with open("/version", "r") as file:
    version = file.read()


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


@app.route("/api/v3/categories", methods=["GET"])
def api_v3_categories():
    return (
        json.dumps(users.CategoriesFrontendGet()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/category/<custom_url>", methods=["GET"])
def api_v3_category(custom_url):
    return (
        json.dumps(users.category_get_by_custom_url(custom_url)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/category/<category_id>/custom_url", methods=["GET"])
def api_v3_category_custom_url(category_id):
    return (
        users.category_get_custom_login_url(category_id),
        200,
        {"Content-Type": "application/json"},
    )
