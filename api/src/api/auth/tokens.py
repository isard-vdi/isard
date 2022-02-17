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
import traceback

from flask import Flask, _request_ctx_stack, jsonify, request
from jose import jwt
from rethinkdb.errors import ReqlTimeoutError

from ..libv2.flask_rethink import RDB
from ..libv2.log import log

db = RDB(app)
db.init_app(app)


def get_header_jwt_payload():
    return get_token_payload(get_token_auth_header())


def get_auto_register_jwt_payload():
    register_payload = get_token_payload(get_token_auth_header())
    login_payload = get_token_payload(get_token_header("Login-Claims"))

    register_payload["role"] = login_payload["role_id"]
    register_payload["group"] = login_payload["group_id"]

    return register_payload


def get_token_header(header):
    """Obtains the Access Token from the a Header"""
    auth = request.headers.get(header, None)
    if not auth:
        raise Error(
            "bad_request",
            "Authorization header is expected",
            traceback.format_stack(),
            request,
        )

    parts = auth.split()
    if parts[0].lower() != "bearer":
        raise Error(
            "bad_request",
            "Authorization header must start with Bearer",
            traceback.format_stack(),
            request,
        )
    elif len(parts) == 1:
        raise Error("bad_request", "Token not found")
    elif len(parts) > 2:
        raise Error(
            "invalid_header",
            "Authorization header must be Bearer token",
            traceback.format_stack(),
            request,
        )

    return parts[1]  # Token


def get_token_auth_header():
    return get_token_header("Authorization")


def get_token_payload(token):
    try:
        claims = jwt.get_unverified_claims(token)
        secret_data = app.ram["secrets"][claims["kid"]]
        # Check if the token has the correct category
        if (
            secret_data["role_id"] == "manager"
            and secret_data["category_id"] != claims["data"]["category_id"]
        ):
            raise Error(
                "unauthorized",
                "Not authorized category token.",
                traceback.format_stack(),
                request,
            )

    except KeyError:
        log.warning(
            "Claim kid "
            + claims["kid"]
            + " does not match any of the current secret ids in database"
        )
    except:
        log.warning("JWT token with invalid parameters. Can not parse it.")
        raise Error(
            "bad_request",
            "Unable to parse authentication parameters token.",
            traceback.format_stack(),
            request,
        )

    try:
        payload = jwt.decode(
            token,
            secret_data["secret"],
            algorithms=["HS256"],
            options=dict(verify_aud=False, verify_sub=False, verify_exp=True),
        )
    except jwt.ExpiredSignatureError:
        log.info("Token expired")
        raise Error(
            "bad_request", "Token is expired", traceback.format_stack(), request
        )
    except jwt.JWTClaimsError:
        raise Error(
            "bad_request",
            "Incorrect claims, please check the audience and issuer",
            traceback.format_stack(),
            request,
        )
    except Exception:
        raise Error(
            "bad_request",
            "Unable to parse authentication token.",
            traceback.format_stack(),
            request,
        )
    if payload.get("data", False):
        return payload["data"]
    return payload
