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

from ..libv2.api_exceptions import Error

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
            "forbidden",
            "Invalid register type token",
            traceback.format_stack(),
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
            "forbidden",
            "Invalid auto register type token",
            traceback.format_stack(),
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
            "forbidden",
            "Not enough rights.",
            traceback.format_stack(),
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
            "forbidden",
            "Not enough rights.",
            traceback.format_stack(),
        )

    return decorated


def is_hyper(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] in ["hypervisor", "admin"]:
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
    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + str(user_id),
        traceback.format_stack(),
    )


def ownsCategoryId(payload, category_id):
    if payload["role_id"] == "admin":
        return True
    if payload["role_id"] == "manager" and category_id == payload["category_id"]:
        return True
    raise Error(
        "forbidden",
        "Not enough access rights for this category_id " + str(category_id),
        traceback.format_stack(),
    )


def ownsDomainId(payload, desktop_id):

    # User is owner
    if desktop_id.startswith("_" + payload["user_id"]):
        return True

    # User is advanced and the desktop is from one of its deployments
    if payload["role_id"] == "advanced":
        with app.app_context():
            desktop_tag = (
                r.table("domains")
                .get(desktop_id)
                .pluck("tag")
                .run(db.conn)
                .get("tag", False)
            )
            if str(desktop_tag).startswith("_" + payload["user_id"]) or str(
                desktop_tag
            ).startswith(payload["user_id"]):
                return True
    # User is manager and the desktop is from its categories
    if (
        payload["role_id"] == "manager"
        and payload["category_id"] == desktop_id.split("-")[1]
    ):
        return True

    # User is admin
    if payload["role_id"] == "admin":
        return True

    raise Error(
        "forbidden",
        "Not enough access rights this desktop_id " + str(desktop_id),
        traceback.format_stack(),
    )


def allowedTemplateId(payload, template_id):
    with app.app_context():
        template = (
            r.table("domains")
            .get(template_id)
            .pluck("user", "allowed", "category")
            .default(None)
            .run(db.conn)
        )
    if not template:
        raise Error(
            "not_found",
            "Not found template_id " + str(template_id),
            traceback.format_stack(),
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
    raise Error(
        "forbidden",
        "Not enough access rights for this template_id " + str(template_id),
        traceback.format_stack(),
    )
