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

# ──────────────────────────────────────────────────────────────────────
# healthcheck — pure smoke route, no auth, no template
# ──────────────────────────────────────────────────────────────────────


def test_healthcheck_returns_empty_200(client):
    response = client.get("/isard-admin/healthcheck")
    assert response.status_code == 200
    assert response.data == b""


# ──────────────────────────────────────────────────────────────────────
# login — POST/GET flows for both default + named-category routes
# ──────────────────────────────────────────────────────────────────────


def test_login_returns_jsonify_success_when_authenticated(
    client, monkeypatch, admin_user_dict
):
    from webapp.auth.authentication import User

    monkeypatch.setattr(
        "webapp.views.AdminViews.get_authenticated_user",
        lambda: User(admin_user_dict),
    )
    response = client.get("/isard-admin/login", headers={"Authorization": "Bearer t"})
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert payload == {"success": True}


def test_login_redirects_when_no_authenticated_user(client, monkeypatch):
    monkeypatch.setattr("webapp.views.AdminViews.get_authenticated_user", lambda: None)
    response = client.get("/isard-admin/login")
    assert response.status_code == 302
    assert response.location == "/login"


def test_login_with_category_path(client, monkeypatch):
    """The /login/<category> variant must use the same code path."""
    monkeypatch.setattr("webapp.views.AdminViews.get_authenticated_user", lambda: None)
    response = client.get("/isard-admin/login/saml-default")
    assert response.status_code == 302
    assert response.location == "/login"


# ──────────────────────────────────────────────────────────────────────
# remote_logout — pure JSON response after logout_user
# ──────────────────────────────────────────────────────────────────────


def test_remote_logout_calls_logout_and_returns_success(client, monkeypatch):
    logout = MagicMock()
    monkeypatch.setattr("webapp.views.AdminViews.logout_user", logout)

    response = client.get("/isard-admin/logout/remote")
    assert response.status_code == 200
    assert json.loads(response.data) == {"success": True}
    logout.assert_called_once_with()


# ──────────────────────────────────────────────────────────────────────
# about — anonymous-allowed page (template render mocked)
# ──────────────────────────────────────────────────────────────────────


def test_about_renders_about_template(client, monkeypatch):
    rendered = MagicMock(return_value="<about-page>")
    monkeypatch.setattr("webapp.views.AdminViews.render_template", rendered)

    response = client.get("/isard-admin/about")
    assert response.status_code == 200
    rendered.assert_called_once()
    args, kwargs = rendered.call_args
    assert args[0] == "pages/about.html"
    assert kwargs["title"] == "About"
    assert kwargs["nav"] == "About"


# ──────────────────────────────────────────────────────────────────────
# 404 / 500 error handlers
# ──────────────────────────────────────────────────────────────────────


def test_404_handler_renders_page_404(client, monkeypatch):
    rendered = MagicMock(return_value="<page-404>")
    monkeypatch.setattr("webapp.render_template", rendered)

    response = client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    rendered.assert_called_once_with("page_404.html")


# ──────────────────────────────────────────────────────────────────────
# admin / admin_landing — require login + isAdmin / isAdminManager
# ──────────────────────────────────────────────────────────────────────


def test_admin_redirects_anonymous_to_login(client):
    response = client.get("/isard-admin/admin")
    # @login_required redirects to login_view ("login") which resolves to /isard-admin/login.
    assert response.status_code == 302
    assert "login" in response.location.lower()


def _patch_login_callback(monkeypatch, user_dict):
    """Replace the Flask-Login user-callback with a stub that returns a User.

    Flask-Login captures the user_loader callback at app-init time, so patching
    the module-level binding does not affect what _load_user actually calls.
    The stable hook is the LoginManager._user_callback attribute itself.
    """
    from webapp.auth.authentication import User

    from webapp import app as flask_app

    monkeypatch.setattr(
        flask_app.login_manager,
        "_user_callback",
        lambda user_id: User(user_dict),
    )


def test_admin_landing_admin_renders_hypervisors(client, monkeypatch, admin_user_dict):
    rendered = MagicMock(return_value="<hypervisors>")
    monkeypatch.setattr("webapp.views.AdminViews.render_template", rendered)
    _patch_login_callback(monkeypatch, admin_user_dict)

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    response = client.get("/isard-admin/admin/landing")
    assert response.status_code == 200
    args, kwargs = rendered.call_args
    assert args[0] == "admin/pages/hypervisors.html"
    assert kwargs["nav"] == "Hypervisors"


def test_admin_landing_manager_renders_analytics(
    client, monkeypatch, manager_user_dict
):
    rendered = MagicMock(return_value="<analytics>")
    monkeypatch.setattr("webapp.views.AdminViews.render_template", rendered)
    _patch_login_callback(monkeypatch, manager_user_dict)

    with client.session_transaction() as sess:
        sess["_user_id"] = manager_user_dict["id"]
        sess["_fresh"] = True

    response = client.get("/isard-admin/admin/landing")
    assert response.status_code == 200
    args, kwargs = rendered.call_args
    assert args[0] == "admin/pages/analytics.html"
    assert kwargs["nav"] == "Analytics"


# ──────────────────────────────────────────────────────────────────────
# logout — JS-redirect HTML with provider + custom_url path build
# ──────────────────────────────────────────────────────────────────────


def test_logout_without_session_cookie_redirects_to_plain_login(
    client, monkeypatch, admin_user_dict
):
    _patch_login_callback(monkeypatch, admin_user_dict)
    requests_get = MagicMock()
    requests_get.return_value.status_code = 200
    requests_get.return_value.text = "ignored-without-cookie"
    monkeypatch.setattr("webapp.views.AdminViews.requests.get", requests_get)
    monkeypatch.setattr(
        "webapp.views.AdminViews.logout_user", MagicMock()
    )  # remote_logout

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    response = client.get("/isard-admin/logout")
    assert response.status_code == 200
    assert b"window.location = '/login'" in response.data
    requests_get.assert_called_once()
    args, _ = requests_get.call_args
    assert "category/default/custom_url" in args[0]


def test_logout_with_local_provider_uses_form_path_and_custom_url(
    client, monkeypatch, admin_user_dict
):
    _patch_login_callback(monkeypatch, admin_user_dict)
    requests_get = MagicMock()
    requests_get.return_value.status_code = 200
    requests_get.return_value.text = "custom-url-1"
    monkeypatch.setattr("webapp.views.AdminViews.requests.get", requests_get)
    token_flask = MagicMock()
    token_flask.get_expired_user_data.return_value = {"provider": "local"}
    monkeypatch.setattr("webapp.views.AdminViews.TokenFlask", token_flask)
    monkeypatch.setattr("webapp.views.AdminViews.logout_user", MagicMock())

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    client.set_cookie(key="isardvdi_session", value="fake-jwt", domain="localhost")
    response = client.get("/isard-admin/logout")
    assert response.status_code == 200
    assert b"window.location = '/login/form/custom-url-1'" in response.data


def test_logout_with_saml_provider_falls_back_when_custom_url_missing(
    client, monkeypatch, admin_user_dict
):
    _patch_login_callback(monkeypatch, admin_user_dict)
    requests_get = MagicMock()
    requests_get.return_value.status_code = 404
    requests_get.return_value.text = "not found"
    monkeypatch.setattr("webapp.views.AdminViews.requests.get", requests_get)
    token_flask = MagicMock()
    token_flask.get_expired_user_data.return_value = {"provider": "saml"}
    monkeypatch.setattr("webapp.views.AdminViews.TokenFlask", token_flask)
    monkeypatch.setattr("webapp.views.AdminViews.logout_user", MagicMock())

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    client.set_cookie(key="isardvdi_session", value="fake-jwt", domain="localhost")
    response = client.get("/isard-admin/logout")
    assert response.status_code == 200
    # 404 from custom_url means we use the bare /login/<provider> path.
    assert b"window.location = '/login/saml'" in response.data


# ──────────────────────────────────────────────────────────────────────
# admin_domains — nav-based template selection (parametrized)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nav,template,icon",
    [
        ("Desktops", "admin/pages/desktops.html", "desktop"),
        ("Templates", "admin/pages/templates.html", "cubes"),
        ("Deployments", "admin/pages/deployments.html", "tv"),
        ("Storage", "admin/pages/storage.html", "folder-open"),
        ("Resources", "admin/pages/domains_resources.html", "arrows-alt"),
        ("Bookables", "admin/pages/bookables.html", "briefcase"),
        ("BookablesEvents", "admin/pages/bookables_events.html", "history"),
        ("Priority", "admin/pages/bookables_priority.html", "briefcase"),
        ("Recyclebin", "admin/pages/recyclebin.html", "trash"),
    ],
)
def test_admin_domains_renders_nav_template(
    client, monkeypatch, admin_user_dict, nav, template, icon
):
    rendered = MagicMock(return_value=f"<{nav}>")
    monkeypatch.setattr("webapp.views.AdminViews.render_template", rendered)
    _patch_login_callback(monkeypatch, admin_user_dict)

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    response = client.get(f"/isard-admin/admin/domains/render/{nav}")
    assert response.status_code == 200
    args, kwargs = rendered.call_args
    assert args[0] == template
    assert kwargs["nav"] == nav
    assert kwargs["icon"] == icon


def test_admin_domains_unknown_nav_falls_through_to_desktops(
    client, monkeypatch, admin_user_dict
):
    """Unknown nav values render the default desktops template (current behaviour)."""
    rendered = MagicMock(return_value="<unknown>")
    monkeypatch.setattr("webapp.views.AdminViews.render_template", rendered)
    _patch_login_callback(monkeypatch, admin_user_dict)

    with client.session_transaction() as sess:
        sess["_user_id"] = admin_user_dict["id"]
        sess["_fresh"] = True

    response = client.get("/isard-admin/admin/domains/render/SomethingNew")
    assert response.status_code == 200
    args, kwargs = rendered.call_args
    assert args[0] == "admin/pages/desktops.html"
    assert kwargs["nav"] == "SomethingNew"


def test_admin_domains_blocks_regular_user(client, monkeypatch, regular_user_dict):
    """A user-role account must be redirected by isAdminManager (not admin/manager)."""
    _patch_login_callback(monkeypatch, regular_user_dict)

    with client.session_transaction() as sess:
        sess["_user_id"] = regular_user_dict["id"]
        sess["_fresh"] = True

    response = client.get("/isard-admin/admin/domains/render/Desktops")
    assert response.status_code == 302
    assert "login" in response.location.lower()
