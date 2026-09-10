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
def mock_admin_get_user_raw(monkeypatch):
    """Stub the generated apiv4 ``admin_get_user_raw.sync_detailed`` +
    ``build_client`` chain that ``user_loader`` / ``user_reloader``
    walk. Replaces the legacy ``mock_api_rest`` fixture — the
    ``ApiRest`` wrapper was removed when commit 0beff7916 migrated
    webapp to the generated apiv4 client.

    Tests configure return values on the returned mock:
        mock_admin_get_user_raw.return_value = MagicMock(
            content=json.dumps({...}).encode("utf-8")
        )
    """
    import contextlib

    sync_detailed = MagicMock()
    monkeypatch.setattr(
        "webapp.auth.authentication.admin_get_user_raw.sync_detailed",
        sync_detailed,
    )
    monkeypatch.setattr(
        "webapp.auth.authentication.build_client",
        lambda *_a, **_kw: contextlib.nullcontext(MagicMock()),
    )
    monkeypatch.setattr(
        "webapp.auth.authentication.raise_for_status", lambda _resp: None
    )
    return sync_detailed


@pytest.fixture()
def mock_get_user_details(monkeypatch):
    """Stub the generated apiv4 ``get_user_details.sync_detailed`` +
    ``build_client`` chain that ``get_authenticated_user`` walks.
    Replaces the legacy ``mock_requests_get`` fixture for the
    auth-side path (``requests.get`` was removed when the same migration
    repointed JWT validation through the generated client)."""
    import contextlib

    sync_detailed = MagicMock()
    monkeypatch.setattr(
        "webapp.auth.authentication.get_user_details.sync_detailed",
        sync_detailed,
    )
    monkeypatch.setattr(
        "webapp.auth.authentication.build_client",
        lambda *_a, **_kw: contextlib.nullcontext(MagicMock()),
    )
    return sync_detailed
