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


@app.route("/api/v3/login", methods=["POST"])
@app.route("/api/v3/login/", methods=["POST"])
@app.route("/api/v3/login/<category_id>", methods=["POST"])
def api_v3_login(category_id="default"):
    try:
        id = request.form.get("usr", type=str)
        passwd = request.form.get("pwd", type=str)

        provider = request.args.get("provider", default="local", type=str)
    except Exception as e:
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "Incorrect access. exception: " + e}
            ),
            401,
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
        id = provider + "-" + category_id + "-" + id + "-" + id
        id_, jwt = users.Login(id, passwd, provider=provider, category_id=category_id)
        return jsonify(success=True, id=id_, jwt=jwt)
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


@app.route("/api/v3/register", methods=["POST"])
def api_v3_register():
    try:
        code = request.form.get("code", type=str)
        domain = request.form.get("email").split("@")[-1]
    except Exception as e:
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "Incorrect access. exception: " + e}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        data = users.CodeSearch(code)
        if check_category_domain(data.get("category"), domain):
            return json.dumps(data), 200, {"Content-Type": "application/json"}
        else:
            log.info(f"Domain {domain} not allowed for category {data.get('category')}")
            return (
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": f"User domain {domain} not allowed",
                    }
                ),
                403,
                {"Content-Type": "application/json"},
            )
    except CodeNotFound:
        log.error("Code not in database.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Code " + code + " not exists in database",
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
                    "msg": "Register general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/category/<id>", methods=["GET"])
def api_v3_category(id):
    try:
        data = users.CategoryGet(id)
        if data.get("frontend", False):
            return json.dumps(data), 200, {"Content-Type": "application/json"}
        return json - dumps({"error": "undefined_error", "msg": "Forbidden"})
    except CategoryNotFound:
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Category " + id + " not exists in database",
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
                    "msg": "Register general exception: " + error,
                }
            ),
            500,
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


@app.route("/api/v3/config", methods=["GET"])
def api_v3_config():
    try:
        socials = []
        if (
            os.environ.get("BACKEND_AUTH_GITHUB_HOST", "") != ""
            and os.environ.get("BACKEND_AUTH_GITHUB_HOST", "") != ""
            and os.environ.get("BACKEND_AUTH_GITHUB_SECRET", "") != ""
        ):
            socials.append("Github")

        if (
            os.environ.get("AUTHENTICATION_AUTENTICATION_GOOGLE_CLIENT_ID", "") != ""
            and os.environ.get("AUTHENTICATION_AUTHENTICATION_GOOGLE_CLIENT_SECRET", "")
            != ""
        ):
            socials.append("Google")

        data = {
            "show_admin_button": os.environ["FRONTEND_SHOW_ADMIN_BTN"],
            "social_logins": socials,
        }
        return json.dumps(data), 200, {"Content-Type": "application/json"}

    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Config general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
