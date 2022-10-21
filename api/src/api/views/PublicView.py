# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import json
import os

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_users import ApiUsers
from ..libv2.log import log

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
