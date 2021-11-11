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

# from flask_cors import cross_origin
from jose import jwt
from rethinkdb.errors import ReqlTimeoutError

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.tokens import AuthError, get_header_jwt_payload
from ..libv2.apiv2_exc import DesktopNotFound, TemplateNotFound

# from ..libv3.api_users import filter_user_templates


def has_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        kwargs["payload"] = payload
        return f(*args, **kwargs)
        raise AuthError(
            {"code": "not_allowed", "description": "Not enough rights" " token."}, 401
        )

    return decorated


def is_register(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") == "register":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise AuthError(
            {"code": "not_allowed", "description": "Not register" " token."}, 401
        )

    return decorated


def is_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise AuthError(
            {"code": "not_allowed", "description": "Not enough rights" " token."}, 401
        )

    return decorated


def is_admin_user(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise AuthError(
            {"code": "not_allowed", "description": "Not enough rights" " token."}, 401
        )

    return decorated


def is_hyper(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        # kwargs['payload']=payload
        return f(*args, **kwargs)

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


# def allowedTemplateId(payload,template_id):
#     if payload['role_id'] == 'admin': return True
#     allowed=r.table('domains').get(template_id).pluck('allowed').run(db.conn)
#     if payload['role_id'] == 'manager' and payload['category_id'] == template_id.split('-')[1]: return True
#     if payload['role_id'] == 'advanced':
#         with app.app_context():
#             if str(r.table('domains').get(template_id).pluck('tag').run(db.conn).get('tag',False)).startswith('_'+payload['user_id']):
#                 return True
#     if template_id.startswith('_'+payload['user_id']): return True
#     return False


def allowedTemplateId(payload, template_id):
    try:
        with app.app_context():
            template = (
                r.table("domains")
                .get(template_id)
                .pluck("allowed", "category")
                .run(db.conn)
            )
    except:
        raise AuthError({"code": 1, "msg": "Not found template " + template_id}, 401)
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


# def allowedId(payload,category_id, alloweds):
#     if payload['role'] == 'admin': return True
#     if payload['role'] == 'manager' and payload['category_id'] == category_id: return True
#     if payload['category_id'] in alloweds['categories']: return True
#     if payload['group_id'] in alloweds['groups']: return True
#     if payload['user_id'] in alloweds['users']: return True
#     return False

# Error handler
# class PermissionError(Exception):
#     def __init__(self, error, status_code):
#         self.error = error
#         self.status_code = status_code

# @app.errorhandler(PermissionError)
# def handle_auth_error(ex):
#     response = jsonify(ex.error)
#     response.status_code = ex.status_code
#     return response
