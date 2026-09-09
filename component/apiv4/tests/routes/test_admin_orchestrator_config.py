# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/orchestrator_config.py — read and write the orchestrator
enabled flag. Both endpoints live on admin_router (admin-only).
"""

from tests.routes.helpers import MockJWT

SERVICE = "api.routes.admin.orchestrator_config.AdminOrchestratorConfigService"


class TestGetOrchestratorConfig:
    URL = "/admin/item/orchestrator-config"

    def test_admin_gets_enabled(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.get_orchestrator_config",
            staticmethod(lambda: True),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"enabled": True}

    def test_admin_gets_disabled(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.get_orchestrator_config",
            staticmethod(lambda: False),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"enabled": False}

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.get_orchestrator_config",
            staticmethod(lambda: True),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.get_orchestrator_config",
            staticmethod(lambda: True),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(f"{SERVICE}.get_orchestrator_config", staticmethod(boom))
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"


class TestUpdateOrchestratorConfig:
    URL = "/admin/item/orchestrator-config"

    def test_admin_disables_the_orchestrator(self, monkeypatch, test_client):
        captured = {}

        def fake_update(enabled):
            captured["enabled"] = enabled

        monkeypatch.setattr(
            f"{SERVICE}.update_orchestrator_config", staticmethod(fake_update)
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 204
        assert captured == {"enabled": False}

    def test_rejects_a_non_boolean_body(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.update_orchestrator_config", staticmethod(lambda enabled: None)
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": "maybe"},
        )
        assert response.status_code in (400, 422)

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            f"{SERVICE}.update_orchestrator_config", staticmethod(lambda enabled: None)
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"enabled": False},
        )
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(enabled):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(f"{SERVICE}.update_orchestrator_config", staticmethod(boom))
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"
