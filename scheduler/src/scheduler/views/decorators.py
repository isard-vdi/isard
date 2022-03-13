# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging
import os
import traceback
from functools import wraps

from flask import Flask, _request_ctx_stack, jsonify, request
from jose import jwt
from rethinkdb import RethinkDB

from scheduler import app

from ..auth.tokens import Error, get_auto_register_jwt_payload, get_header_jwt_payload
from ..lib.exceptions import Error


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
