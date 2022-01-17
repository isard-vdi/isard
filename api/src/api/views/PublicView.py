# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

import json
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import jsonify, request

from api import app

from ..libv2.api_users import ApiUsers, check_category_domain
from ..libv2.apiv2_exc import *
from ..libv2.log import log

users = ApiUsers()


@app.route("/api/v3", methods=["GET"])
def api_v3_test():
    with open("/version", "r") as file:
        version = file.read()
    return (
        json.dumps(
            {"name": "IsardVDI", "api_version": 3.1, "isardvdi_version": version}
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/categories", methods=["GET"])
def api_v3_categories():
    try:
        return (
            json.dumps(users.CategoriesFrontendGet()),
            200,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "CategoriesGet general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
