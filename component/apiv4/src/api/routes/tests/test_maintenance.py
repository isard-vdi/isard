#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

import pytest
from api.routes.tests.helpers import MockJWT


@pytest.mark.clear_cache
def test_maintenance_status_disabled_by_default(test_client):
    """Default config (maintenance: False) → /maintenance/status returns False."""
    jwt = MockJWT()

    response = test_client(
        method="GET", url="/maintenance/status", jwt=jwt, remove_default_db=True
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.clear_cache
def test_maintenance_status_reflects_service(monkeypatch, test_client):
    """When MaintenanceService.is_enabled() returns True, the route mirrors it."""
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.is_enabled",
        staticmethod(lambda: True),
    )
    jwt = MockJWT()
    response = test_client(method="GET", url="/maintenance/status", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


@pytest.mark.clear_cache
def test_get_maintenance_admin_always_sees_disabled(monkeypatch, test_client):
    """The /maintenance endpoint short-circuits to False for admin role,
    even when global maintenance is enabled — admins must keep working."""
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.is_enabled",
        staticmethod(lambda: True),
    )
    jwt = MockJWT(role_id="admin")
    response = test_client(url="/maintenance", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


@pytest.mark.clear_cache
def test_get_maintenance_user_sees_global_or_category_status(monkeypatch, test_client):
    """Non-admin: enabled = global OR category."""
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.is_enabled",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.get_category_status",
        staticmethod(lambda category_id: True),
    )
    jwt = MockJWT(role_id="user", category_id="cat-down")
    response = test_client(url="/maintenance", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


@pytest.mark.clear_cache
def test_update_maintenance_persists_via_service(monkeypatch, test_client):
    """PUT /maintenance forwards the status flag to set_enabled and returns
    the new status from is_enabled — pin the read-after-write contract."""
    state = {"enabled": False}

    def fake_set(enabled):
        state["enabled"] = enabled

    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.set_enabled",
        staticmethod(fake_set),
    )
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.is_enabled",
        staticmethod(lambda: state["enabled"]),
    )
    jwt = MockJWT(role_id="admin")
    response = test_client(
        method="PUT", url="/maintenance", body={"enabled": True}, jwt=jwt
    )
    assert response.status_code == 200
    assert response.json() == {"enabled": True}
    assert state["enabled"] is True


@pytest.mark.clear_cache
def test_get_category_maintenance_admin_only(monkeypatch, test_client):
    """admin_router rejects role=user even on read endpoints."""
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.is_enabled",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        "api.services.maintenance.MaintenanceService.get_category_status",
        staticmethod(lambda category_id: False),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/maintenance/cat-1", jwt=jwt)
    assert response.status_code == 403
