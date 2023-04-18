# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import os
import traceback
from functools import wraps

from engine.services.db.db import get_isardvdi_secret, update_table_field
from engine.services.log import logs
from flask import request
from jose import jwt

from .exceptions import Error

api_secret = get_isardvdi_secret()


def get_header_jwt_payload():
    return get_token_payload(get_token_auth_header())


def get_token_header(header):
    """Obtains the Access Token from the a Header"""
    auth = request.headers.get(header, None)
    if not auth:
        raise Error(
            "unauthorized",
            "Authorization header is expected",
            traceback.format_stack(),
        )

    parts = auth.split()
    if parts[0].lower() != "bearer":
        raise Error(
            "unauthorized",
            "Authorization header must start with Bearer",
            traceback.format_stack(),
        )
    elif len(parts) == 1:
        raise Error("bad_request", "Token not found")
    elif len(parts) > 2:
        raise Error(
            "unauthorized",
            "Authorization header must be Bearer token",
            traceback.format_stack(),
        )

    return parts[1]  # Token


def get_token_auth_header():
    return get_token_header("Authorization")


def get_token_payload(token):
    try:
        payload = jwt.decode(
            token,
            api_secret,
            algorithms=["HS256"],
            options=dict(verify_aud=False, verify_sub=False, verify_exp=True),
        )
    except jwt.ExpiredSignatureError:
        logs.main.info("Token expired")
        raise Error("unauthorized", "Token is expired", traceback.format_stack())
    except jwt.JWTClaimsError:
        raise Error(
            "unauthorized",
            "Incorrect claims, please check the audience and issuer",
            traceback.format_stack(),
        )
    except Exception:
        raise Error(
            "unauthorized",
            "Unable to parse authentication token.",
            traceback.format_stack(),
        )
    if payload.get("data", False):
        return payload["data"]
    return payload


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
