# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/smtp.py — SMTP configuration get/put, enabled flag,
test-connection. All endpoints live on admin_router (admin-only).

GET endpoints (`/smtp`, `/smtp/enabled`) are wrapped in
`@cached(cache=TTLCache(...))` so cross-test pollution is possible —
the test_client fixture uses MockJWT(category_id="default") which
matches the seeded default category, but tests still need
``@pytest.mark.clear_cache`` when they monkeypatch the service and
expect the new return value to be observed (per Critical gotcha 5
in the testing skill).
"""

import pytest
from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /smtp — TTLCache-wrapped
# ══════════════════════════════════════════════════════════════════════════


class TestGetSmtpConfig:
    URL = "/smtp"

    @pytest.mark.clear_cache
    def test_admin_gets_config(self, monkeypatch, test_client):
        sample = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "isardvdi",
            "enabled": True,
        }
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_config",
            staticmethod(lambda: sample),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["host"] == "smtp.example.com"
        # Password must NEVER appear on GET — sanity-check the wire shape.
        assert "password" not in response.json()

    @pytest.mark.clear_cache
    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    @pytest.mark.clear_cache
    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /smtp
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateSmtpConfig:
    URL = "/smtp"

    def test_admin_updates_config(self, monkeypatch, test_client):
        captured = {}

        def fake_update(data):
            captured["data"] = data
            return {**data, "saved": True}

        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.update_smtp_config",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "host": "smtp.example.com",
                "port": 587,
                "username": "u",
                "password": "p",
                "enabled": True,
            },
        )
        assert response.status_code == 200
        # exclude_none means a missing field is dropped, but `enabled: True`
        # is not None so it survives.
        assert captured["data"]["enabled"] is True
        assert captured["data"]["password"] == "p"

    def test_admin_omitting_optional_fields_passes_through(
        self, monkeypatch, test_client
    ):
        """exclude_none=True drops fields whose value is exactly None,
        so a partial update payload reaches the service with only the
        fields the admin actually set."""
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.update_smtp_config",
            staticmethod(lambda data: captured.update(data=data) or {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 200
        assert captured["data"] == {"enabled": False}

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.update_smtp_config",
            staticmethod(lambda data: {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"enabled": True},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.update_smtp_config",
            staticmethod(lambda data: {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"enabled": True},
        )
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(data):
            raise Error("bad_request", "Invalid SMTP config")

        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.update_smtp_config",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"port": 25},
        )
        assert response.status_code == 400

    def test_invalid_port_type_rejected(self, test_client):
        """port must coerce to int — an obviously-wrong type → 422."""
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"port": "not-a-number"},
        )
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  GET /smtp/enabled — TTLCache-wrapped
# ══════════════════════════════════════════════════════════════════════════


class TestGetSmtpEnabled:
    URL = "/smtp/enabled"

    @pytest.mark.clear_cache
    def test_admin_gets_enabled(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_enabled",
            staticmethod(lambda: True),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() is True

    @pytest.mark.clear_cache
    def test_admin_gets_disabled(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_enabled",
            staticmethod(lambda: False),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() is False

    @pytest.mark.clear_cache
    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.get_smtp_enabled",
            staticmethod(lambda: False),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /smtp/test
# ══════════════════════════════════════════════════════════════════════════


class TestTestSmtp:
    URL = "/smtp/test"

    def test_admin_test_returns_result(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.test_smtp",
            staticmethod(lambda data: {"result": True}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"host": "smtp.example.com", "port": 587},
        )
        assert response.status_code == 200
        # response_model fills the optional ``error`` field with None when
        # the service didn't include it, so we assert the success bit only.
        assert response.json()["result"] is True

    def test_failed_smtp_includes_error_in_response(self, monkeypatch, test_client):
        """The endpoint returns 200 with `{result: false, error: ...}` when
        the connection itself fails — the API call succeeded, the SMTP
        connection didn't. Don't promote a connection failure to HTTP 500.
        """
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.test_smtp",
            staticmethod(lambda data: {"result": False, "error": "auth failed"}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"host": "smtp.example.com", "port": 25, "username": "x"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"] is False
        assert body["error"] == "auth failed"

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.test_smtp",
            staticmethod(lambda data: {"result": True}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"host": "smtp.example.com"},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.test_smtp",
            staticmethod(lambda data: {"result": True}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"host": "smtp.example.com"},
        )
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(data):
            raise RuntimeError("crash inside service")

        monkeypatch.setattr(
            "api.routes.admin.smtp.AdminSmtpService.test_smtp",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"host": "smtp.example.com"},
        )
        assert response.status_code == 500
