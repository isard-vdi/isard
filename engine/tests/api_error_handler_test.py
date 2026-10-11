# SPDX-License-Identifier: AGPL-3.0-or-later
"""The engine API answers its own errors with their status, not a 500."""

import time

import jwt
import pytest
from flask import Flask

from engine import api as engine_api
from engine.api import tokens

SECRET = "test-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(tokens, "api_secret", SECRET)
    app = Flask(__name__)
    app.register_blueprint(engine_api.api)
    return app.test_client()


def _bearer(**claims):
    return {"Authorization": "Bearer " + jwt.encode(claims, SECRET, algorithm="HS256")}


def test_missing_token_is_401(client):
    response = client.get("/engine/status")

    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_expired_token_is_401(client):
    headers = _bearer(exp=int(time.time()) - 60, data={"role_id": "admin"})

    response = client.get("/engine/status", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["description"] == "Token is expired"


def test_non_admin_is_403(client):
    headers = _bearer(exp=int(time.time()) + 60, data={"role_id": "user"})

    response = client.get("/engine/status", headers=headers)

    assert response.status_code == 403


def test_error_body_carries_no_stack_or_request_headers(client):
    body = client.get("/engine/status").get_json()

    assert set(body) <= {"error", "msg", "description"}
