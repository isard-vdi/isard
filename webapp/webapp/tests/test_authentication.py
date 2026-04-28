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

import json
from unittest.mock import MagicMock

import pytest

from webapp.auth.authentication import (
    User,
    get_authenticated_user,
    user_loader,
    user_reloader,
)

# ──────────────────────────────────────────────────────────────────────
# User class
# ──────────────────────────────────────────────────────────────────────


def test_user_admin_is_admin_true(admin_user_dict):
    user = User(admin_user_dict)
    assert user.id == "admin-user-id"
    assert user.role == "admin"
    assert user.is_admin is True
    assert user.category == "default"
    assert user.name == "Admin User"
    assert user.username == "admin"


@pytest.mark.parametrize("role", ["manager", "advanced", "user"])
def test_user_non_admin_is_admin_false(role):
    user = User(
        {
            "id": "x",
            "role": role,
            "category": "default",
            "name": f"{role} user",
            "username": role,
        }
    )
    assert user.role == role
    assert user.is_admin is False


def test_user_is_anonymous_is_false(admin_user_dict):
    user = User(admin_user_dict)
    assert user.is_anonymous() is False


def test_user_get_id_returns_id(admin_user_dict):
    """UserMixin.get_id() is what flask_login uses for session storage."""
    user = User(admin_user_dict)
    assert user.get_id() == "admin-user-id"


# ──────────────────────────────────────────────────────────────────────
# get_authenticated_user
# ──────────────────────────────────────────────────────────────────────


def test_get_authenticated_user_returns_none_without_authorization_header(app):
    with app.test_request_context("/", headers={}):
        result = get_authenticated_user()
    assert result is None


def test_get_authenticated_user_returns_user_on_200(
    app, mock_requests_get, admin_user_dict
):
    response = MagicMock()
    response.status_code = 200
    response.text = json.dumps(admin_user_dict)
    mock_requests_get.return_value = response

    with app.test_request_context("/", headers={"Authorization": "Bearer token-1"}):
        result = get_authenticated_user()

    assert isinstance(result, User)
    assert result.id == "admin-user-id"
    assert result.is_admin is True
    mock_requests_get.assert_called_once_with(
        "http://isard-apiv4:5000/api/v4/item/user/get-details",
        headers={"Authorization": "Bearer token-1"},
        timeout=5,
    )


def test_get_authenticated_user_returns_none_on_non_200(app, mock_requests_get):
    response = MagicMock()
    response.status_code = 401
    response.text = ""
    mock_requests_get.return_value = response

    with app.test_request_context("/", headers={"Authorization": "Bearer bad-token"}):
        result = get_authenticated_user()

    assert result is None


# ──────────────────────────────────────────────────────────────────────
# user_loader / user_reloader (Flask-Login session restore)
# ──────────────────────────────────────────────────────────────────────


def test_user_loader_returns_user_on_success(app, mock_api_rest, admin_user_dict):
    mock_api_rest.get.return_value = admin_user_dict

    with app.test_request_context("/"):
        result = user_loader("admin-user-id")

    assert isinstance(result, User)
    assert result.id == "admin-user-id"
    mock_api_rest.get.assert_called_once_with("/admin/user/admin-user-id/raw")


def test_user_loader_returns_none_when_api_returns_none(app, mock_api_rest):
    mock_api_rest.get.return_value = None

    with app.test_request_context("/"):
        result = user_loader("missing-user-id")

    assert result is None


def test_user_loader_returns_maintenance_response_on_exception(
    app, mock_api_rest, monkeypatch
):
    mock_api_rest.get.side_effect = RuntimeError("apiv4 down")
    rendered = MagicMock(return_value="<maintenance-html>")
    monkeypatch.setattr("webapp.auth.authentication.render_template", rendered)

    with app.test_request_context("/"):
        result = user_loader("any-id")

    body, status = result
    assert status == 503
    assert body == "<maintenance-html>"
    rendered.assert_called_once_with("maintenance.html")


def test_user_reloader_returns_user_on_success(app, mock_api_rest, manager_user_dict):
    mock_api_rest.get.return_value = manager_user_dict

    with app.test_request_context("/"):
        result = user_reloader("manager-user-id")

    assert isinstance(result, User)
    assert result.role == "manager"
    assert result.is_admin is False
