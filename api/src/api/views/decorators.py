# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import os
from functools import wraps

from flask import request
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging
import traceback

from flask import Flask, _request_ctx_stack, jsonify, request
from jose import jwt
from rethinkdb.errors import ReqlTimeoutError

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.tokens import Error, get_auto_register_jwt_payload, get_header_jwt_payload
from ..libv2.apiv2_exc import DesktopNotFound, TemplateNotFound


def has_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def is_register(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") == "register":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            {"error": "not_allowed", "description": "Not register" " token."}, 401
        )

    return decorated


def is_auto_register(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_auto_register_jwt_payload()
        if payload.get("type", "") == "register":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            {"error": "not_allowed", "description": "Not register" " token."}, 401
        )

    return decorated


def is_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            {"error": "not_allowed", "description": "Not enough rights" " token."}, 403
        )

    return decorated


def is_admin_or_manager(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin" or payload["role_id"] == "manager":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            {"error": "not_allowed", "description": "Not enough rights" " token."}, 403
        )

    return decorated


def is_hyper(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "hypervisor":
            return f(*args, **kwargs)
        raise Error(
            {"error": "forbidden", "description": "Not enough rights" " token."}, 403
        )

    return decorated


### Helpers
def ownsUserId(payload, user_id):
    if payload["role_id"] == "admin":
        return True
    if (
        payload["role_id"] == "manager"
        and user_id.split["-"][1] == payload["category_id"]
    ):
        return True
    if payload["user_id"] == user_id:
        return True
    return False


def ownsCategoryId(payload, category_id):
    if payload["role_id"] == "admin":
        return True
    if payload["role_id"] == "manager" and category_id == payload["category_id"]:
        return True
    return False


def ownsDomainId(payload, desktop_id):
    if payload["role_id"] == "admin":
        return True
    if (
        payload["role_id"] == "manager"
        and payload["category_id"] == desktop_id.split("-")[1]
    ):
        return True
    if payload["role_id"] == "advanced":
        with app.app_context():
            if str(
                r.table("domains")
                .get(desktop_id)
                .pluck("tag")
                .run(db.conn)
                .get("tag", False)
            ).startswith("_" + payload["user_id"]):
                return True
    if desktop_id.startswith("_" + payload["user_id"]):
        return True
    return False


def allowedTemplateId(payload, template_id):
    try:
        with app.app_context():
            template = (
                r.table("domains")
                .get(template_id)
                .pluck("user", "allowed", "category")
                .run(db.conn)
            )
    except:
        raise Error(
            {
                "error": "template_not_found",
                "msg": "Not found template " + template_id,
            },
            404,
        )
    if payload["user_id"] == template["user"]:
        return True
    alloweds = template["allowed"]
    if payload["role_id"] == "admin":
        return True
    if (
        payload["role_id"] == "manager"
        and payload["category_id"] == template["category"]
    ):
        return True
    if alloweds["roles"] != False:
        if alloweds["roles"] == []:
            return True
        if payload["role_id"] in alloweds["roles"]:
            return True
    if alloweds["categories"] != False:
        if alloweds["categories"] == []:
            return True
        if payload["category_id"] in alloweds["categories"]:
            return True
    if alloweds["groups"] != False:
        if alloweds["groups"] == []:
            return True
        if payload["group_id"] in alloweds["groups"]:
            return True
    if alloweds["users"] != False:
        if alloweds["users"] == []:
            return True
        if payload["user_id"] in alloweds["users"]:
            return True
    return False
