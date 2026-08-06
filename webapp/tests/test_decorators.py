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

from unittest.mock import MagicMock

import pytest

from webapp.views.decorators import (
    _get_maintenance,
    isAdmin,
    isAdminManager,
    maintenance,
)


def _patch_current_user(monkeypatch, **attrs):
    """Replace flask_login current_user proxy in decorators module with a mock."""
    user = MagicMock(**attrs)
    monkeypatch.setattr("webapp.views.decorators.current_user", user)
    return user


def _patch_logout(monkeypatch):
    logout = MagicMock()
    monkeypatch.setattr("webapp.views.decorators.logout_user", logout)
    return logout


# ──────────────────────────────────────────────────────────────────────
# isAdmin
# ──────────────────────────────────────────────────────────────────────


def test_is_admin_allows_admin_user(app, monkeypatch):
    _patch_current_user(monkeypatch, is_admin=True, role="admin")
    logout = _patch_logout(monkeypatch)

    @isAdmin
    def view():
        return "admin-content"

    with app.test_request_context():
        result = view()

    assert result == "admin-content"
    logout.assert_not_called()


def test_is_admin_redirects_non_admin_user(app, monkeypatch):
    _patch_current_user(monkeypatch, is_admin=False, role="manager")
    logout = _patch_logout(monkeypatch)

    @isAdmin
    def view():  # pragma: no cover — should not be called
        return "should-not-execute"

    with app.test_request_context():
        response = view()

    assert response.status_code == 302
    assert response.location == "/login"
    logout.assert_called_once_with()


def test_is_admin_passes_args_and_kwargs(app, monkeypatch):
    _patch_current_user(monkeypatch, is_admin=True, role="admin")
    _patch_logout(monkeypatch)

    received = {}

    @isAdmin
    def view(category, nav=None):
        received["category"] = category
        received["nav"] = nav
        return "ok"

    with app.test_request_context():
        result = view("default", nav="Hypervisors")

    assert result == "ok"
    assert received == {"category": "default", "nav": "Hypervisors"}


# ──────────────────────────────────────────────────────────────────────
# isAdminManager
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role,is_admin", [("admin", True), ("manager", False)])
def test_is_admin_manager_allows_admin_and_manager(app, monkeypatch, role, is_admin):
    _patch_current_user(monkeypatch, is_admin=is_admin, role=role)
    logout = _patch_logout(monkeypatch)

    @isAdminManager
    def view():
        return f"{role}-content"

    with app.test_request_context():
        result = view()

    assert result == f"{role}-content"
    logout.assert_not_called()


@pytest.mark.parametrize("role", ["advanced", "user"])
def test_is_admin_manager_blocks_advanced_and_user(app, monkeypatch, role):
    _patch_current_user(monkeypatch, is_admin=False, role=role)
    logout = _patch_logout(monkeypatch)

    @isAdminManager
    def view():  # pragma: no cover — should not be called
        return "should-not-execute"

    with app.test_request_context():
        response = view()

    assert response.status_code == 302
    assert response.location == "/login"
    logout.assert_called_once_with()


# ──────────────────────────────────────────────────────────────────────
# maintenance
# ──────────────────────────────────────────────────────────────────────


def test_maintenance_passes_through_when_off(app, monkeypatch):
    _patch_current_user(monkeypatch, role="user", category="default")
    monkeypatch.setattr(
        "webapp.views.decorators._get_maintenance",
        lambda category_id=None: False,
    )

    @maintenance
    def view():
        return "live-content"

    with app.test_request_context():
        result = view()

    assert result == "live-content"


def test_maintenance_returns_503_for_non_admin_when_on(app, monkeypatch):
    _patch_current_user(monkeypatch, role="user", category="default")
    monkeypatch.setattr(
        "webapp.views.decorators._get_maintenance",
        lambda category_id=None: True,
    )
    rendered = MagicMock(return_value="<maintenance-html>")
    monkeypatch.setattr("webapp.views.decorators.render_template", rendered)

    @maintenance
    def view():  # pragma: no cover — should not execute when in maintenance
        return "live-content"

    with app.test_request_context():
        body, status = view()

    assert status == 503
    assert body == "<maintenance-html>"
    rendered.assert_called_once_with("maintenance.html")


def test_maintenance_bypasses_for_admin(app, monkeypatch):
    _patch_current_user(monkeypatch, role="admin", category="default")
    monkeypatch.setattr(
        "webapp.views.decorators._get_maintenance",
        lambda category_id=None: True,
    )

    @maintenance
    def view():
        return "admin-bypass"

    with app.test_request_context():
        result = view()

    assert result == "admin-bypass"


def test_maintenance_uses_user_category(app, monkeypatch):
    _patch_current_user(monkeypatch, role="manager", category="finance")
    seen = {}

    def fake_get_maintenance(category_id=None):
        seen["category_id"] = category_id
        return False

    monkeypatch.setattr(
        "webapp.views.decorators._get_maintenance", fake_get_maintenance
    )

    @maintenance
    def view():
        return "manager-content"

    with app.test_request_context():
        result = view()

    assert result == "manager-content"
    assert seen == {"category_id": "finance"}


# ──────────────────────────────────────────────────────────────────────
# _get_maintenance — cached helper
# ──────────────────────────────────────────────────────────────────────


def _patch_maintenance_clients(monkeypatch, *, parsed):
    """Stub the generated apiv4 client wiring ``_get_maintenance`` uses.

    The legacy ``ApiRest`` wrapper was replaced by ``build_client`` +
    ``get_category_maintenance.sync_detailed`` / ``maintenance_status.sync_detailed``
    when commit 0beff7916 migrated webapp to the generated client.

    Returns the (with_category, without_category) sync_detailed mocks so
    each test can assert which one was called.
    """
    import contextlib

    with_cat = MagicMock(return_value=MagicMock(parsed=parsed))
    without_cat = MagicMock(return_value=MagicMock(parsed=parsed))
    monkeypatch.setattr(
        "webapp.views.decorators.get_category_maintenance.sync_detailed", with_cat
    )
    monkeypatch.setattr(
        "webapp.views.decorators.maintenance_status.sync_detailed", without_cat
    )
    monkeypatch.setattr(
        "webapp.views.decorators.build_client",
        lambda *_a, **_kw: contextlib.nullcontext(MagicMock()),
    )
    monkeypatch.setattr("webapp.views.decorators.raise_for_status", lambda _resp: None)
    return with_cat, without_cat


def test_get_maintenance_returns_false_on_disabled(monkeypatch):
    """Generated client returns a typed ``MaintenanceStatusResponse``;
    ``_get_maintenance`` reads ``.enabled`` and coerces to bool."""
    from isardvdi_apiv4_client.models import MaintenanceStatusResponse

    with_cat, _ = _patch_maintenance_clients(
        monkeypatch, parsed=MaintenanceStatusResponse(enabled=False)
    )
    _get_maintenance.cache_clear()

    assert _get_maintenance("test-cat-1") is False
    with_cat.assert_called_once()
    _get_maintenance.cache_clear()


def test_get_maintenance_returns_true_on_enabled(monkeypatch):
    from isardvdi_apiv4_client.models import MaintenanceStatusResponse

    _patch_maintenance_clients(
        monkeypatch, parsed=MaintenanceStatusResponse(enabled=True)
    )
    _get_maintenance.cache_clear()

    assert _get_maintenance("test-cat-2") is True
    _get_maintenance.cache_clear()


def test_get_maintenance_handles_dict_response(monkeypatch):
    """Backwards-compat: if ``parsed`` is a plain dict (older client
    version or codegen flag flip) the helper falls back to
    ``result.get("enabled")`` so it still produces a usable bool."""
    _patch_maintenance_clients(monkeypatch, parsed={"enabled": True})
    _get_maintenance.cache_clear()

    assert _get_maintenance("test-cat-3") is True
    _get_maintenance.cache_clear()


def test_get_maintenance_no_category(monkeypatch):
    """``category_id=None`` routes through ``maintenance_status``
    (the bare ``/maintenance`` path) rather than the per-category
    endpoint — pin the branch."""
    from isardvdi_apiv4_client.models import MaintenanceStatusResponse

    with_cat, without_cat = _patch_maintenance_clients(
        monkeypatch, parsed=MaintenanceStatusResponse(enabled=False)
    )
    _get_maintenance.cache_clear()

    assert _get_maintenance() is False
    without_cat.assert_called_once()
    with_cat.assert_not_called()
    _get_maintenance.cache_clear()
