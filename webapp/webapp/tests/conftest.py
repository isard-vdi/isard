#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
from unittest.mock import MagicMock

# Force production-mode behaviour (no /tmp secret file write) before importing app.
os.environ.setdefault("USAGE", "test")
os.environ.setdefault("DOMAIN", "localhost")
# isardvdi_common.connections.api_rest.header_auth reads this at first call —
# even tests that mock ApiRest can fail in error paths if the env var is unset.
os.environ.setdefault("API_ISARDVDI_SECRET", "test-secret")

import pytest
from flask_login import login_user

from webapp import app as flask_app
from webapp.auth.authentication import User


@pytest.fixture()
def app():
    """Flask app under test with TESTING enabled."""
    flask_app.config["TESTING"] = True
    flask_app.config["LOGIN_DISABLED"] = False
    return flask_app


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def admin_user_dict():
    return {
        "id": "admin-user-id",
        "role": "admin",
        "category": "default",
        "name": "Admin User",
        "username": "admin",
    }


@pytest.fixture()
def manager_user_dict():
    return {
        "id": "manager-user-id",
        "role": "manager",
        "category": "default",
        "name": "Manager User",
        "username": "manager",
    }


@pytest.fixture()
def advanced_user_dict():
    return {
        "id": "advanced-user-id",
        "role": "advanced",
        "category": "default",
        "name": "Advanced User",
        "username": "advanced",
    }


@pytest.fixture()
def regular_user_dict():
    return {
        "id": "regular-user-id",
        "role": "user",
        "category": "default",
        "name": "Regular User",
        "username": "user",
    }


def _login(client, app, user_dict):
    """Log in via Flask-Login session inside the test client."""
    user = User(user_dict)
    with client.session_transaction():
        pass
    with app.test_request_context():
        login_user(user)
    return user


@pytest.fixture()
def login_as(app, client):
    """Helper that logs in any User dict for the test client session."""

    def _do(user_dict):
        with client.session_transaction() as sess:
            sess["_user_id"] = user_dict["id"]
            sess["_fresh"] = True
        return User(user_dict)

    return _do


@pytest.fixture(autouse=True)
def disable_maintenance(monkeypatch):
    """All tests run with maintenance off unless explicitly overridden."""
    monkeypatch.setattr(
        "webapp.views.decorators._get_maintenance",
        lambda category_id=None: False,
    )


@pytest.fixture()
def mock_api_rest(monkeypatch):
    """Patches isardvdi_common.connections.api_rest.ApiRest with a MagicMock instance.

    Returns the mock instance. Tests configure return values on it directly:
        mock_api_rest.get.return_value = {"id": "x", ...}
    """
    instance = MagicMock()
    factory = MagicMock(return_value=instance)
    # Patch the ApiRest class wherever it is imported in webapp modules.
    monkeypatch.setattr("isardvdi_common.connections.api_rest.ApiRest", factory)
    monkeypatch.setattr("webapp.views.decorators.ApiRest", factory, raising=False)
    monkeypatch.setattr("webapp.auth.authentication.ApiRest", factory, raising=False)
    return instance


@pytest.fixture()
def mock_requests_get(monkeypatch):
    """Patches requests.get used by webapp.auth.authentication and AdminViews."""
    mock = MagicMock()
    monkeypatch.setattr("webapp.auth.authentication.requests.get", mock)
    monkeypatch.setattr("webapp.views.AdminViews.requests.get", mock, raising=False)
    return mock
