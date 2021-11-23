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


@app.route("/api/v3/login_ldap", methods=["POST"])
def api_v3_login_ldap():
    try:
        id = request.form.get("id", type=str)
        passwd = request.form.get("passwd", type=str)
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Incorrect access. exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
    if id == None or passwd == None:
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

    try:
        id_ = users.LoginLdap(id, passwd)
        return json.dumps({"id": id_}), 200, {"Content-Type": "application/json"}
    except UserLoginFailed:
        log.error("User " + id + " login failed.")
        return (
            json.dumps({"error": "undefined_error", "msg": "User login failed"}),
            403,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "UserExists general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


# Used by frontend to get categories dropdown values
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
