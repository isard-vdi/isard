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
from flask import g
from werkzeug.exceptions import ServiceUnavailable

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


def _resp(status_code, body):
    """Build a MagicMock that looks like a generated-client response.

    ``content`` is what the route handlers decode + json.loads, so pin
    the bytes shape (the codegen currently produces bytes)."""
    r = MagicMock()
    r.status_code = status_code
    r.content = json.dumps(body).encode("utf-8") if body is not None else b""
    return r


def test_get_authenticated_user_returns_user_on_200(
    app, mock_get_user_details, admin_user_dict
):
    mock_get_user_details.return_value = _resp(200, admin_user_dict)

    with app.test_request_context("/", headers={"Authorization": "Bearer token-1"}):
        result = get_authenticated_user()

    assert isinstance(result, User)
    assert result.id == "admin-user-id"
    assert result.is_admin is True
    mock_get_user_details.assert_called_once()


def test_get_authenticated_user_returns_none_on_non_200(app, mock_get_user_details):
    mock_get_user_details.return_value = _resp(401, None)

    with app.test_request_context("/", headers={"Authorization": "Bearer bad-token"}):
        result = get_authenticated_user()

    assert result is None


# ──────────────────────────────────────────────────────────────────────
# user_loader / user_reloader (Flask-Login session restore)
# ──────────────────────────────────────────────────────────────────────


def test_user_loader_returns_user_on_success(
    app, mock_admin_get_user_raw, admin_user_dict
):
    mock_admin_get_user_raw.return_value = _resp(200, admin_user_dict)

    with app.test_request_context("/"):
        result = user_loader("admin-user-id")

    assert isinstance(result, User)
    assert result.id == "admin-user-id"
    mock_admin_get_user_raw.assert_called_once()
    # Pin that the user_id is forwarded as a kwarg — codegen contract.
    assert mock_admin_get_user_raw.call_args.kwargs.get("user_id") == "admin-user-id"


def test_user_loader_returns_none_when_api_returns_none(app, mock_admin_get_user_raw):
    """Empty response body → ``json.loads`` returns ``None`` → user_loader
    returns ``None`` (not a maintenance response)."""
    mock_admin_get_user_raw.return_value = MagicMock(status_code=200, content=b"")

    with app.test_request_context("/"):
        result = user_loader("missing-user-id")

    assert result is None


def test_user_loader_aborts_503_when_api_unreachable(app, mock_admin_get_user_raw):
    """apiv4 unreachable → ``abort(503)`` (NOT ``render_template`` inside
    the loader, which recurses through Flask-Login's context processor).
    The sticky ``g`` flag is set so the 503 handler's maintenance render
    can re-enter the loader without re-aborting."""
    mock_admin_get_user_raw.side_effect = RuntimeError("apiv4 down")

    with app.test_request_context("/"):
        with pytest.raises(ServiceUnavailable):
            user_loader("any-id")
        assert g.get("_isard_api_unreachable") is True


def test_user_loader_short_circuits_when_api_already_unreachable(
    app, mock_admin_get_user_raw
):
    """Once the request is flagged api-unreachable, the loader returns
    ``None`` immediately and does NOT call apiv4 again — this is what
    breaks the render→context-processor→loader recursion cycle."""
    with app.test_request_context("/"):
        g._isard_api_unreachable = True
        assert user_loader("any-id") is None
        mock_admin_get_user_raw.assert_not_called()


def test_maintenance_page_served_without_recursion(client, mock_admin_get_user_raw):
    """End-to-end regression for the RecursionError: a request whose
    template/decorator touches ``current_user`` while apiv4 is down must
    render maintenance.html with 503 — the loader aborts, the 503 handler
    renders maintenance, and its context processor re-enters the loader
    once (short-circuited by the sticky ``g`` flag) instead of recursing
    until the stack blows."""
    mock_admin_get_user_raw.side_effect = RuntimeError("apiv4 down")
    with client.session_transaction() as sess:
        sess["_user_id"] = "any-id"

    resp = client.get("/isard-admin/about")

    assert resp.status_code == 503
    # The recursion previously surfaced as a RecursionError 500.
    assert mock_admin_get_user_raw.call_count == 1


def test_user_reloader_returns_user_on_success(
    app, mock_admin_get_user_raw, manager_user_dict
):
    mock_admin_get_user_raw.return_value = _resp(200, manager_user_dict)

    with app.test_request_context("/"):
        result = user_reloader("manager-user-id")

    assert isinstance(result, User)
    assert result.role == "manager"
    assert result.is_admin is False


def test_user_reloader_aborts_503_when_api_unreachable(app, mock_admin_get_user_raw):
    mock_admin_get_user_raw.side_effect = RuntimeError("apiv4 down")

    with app.test_request_context("/"):
        with pytest.raises(ServiceUnavailable):
            user_reloader("any-id")
        assert g.get("_isard_api_unreachable") is True
