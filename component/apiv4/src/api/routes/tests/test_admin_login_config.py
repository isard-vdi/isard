# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/login_config.py — global login-notification update +
per-section enable toggles. All endpoints live on admin_router.

Note: per-category login_config (the `/admin/category/{id}/login_notification`
surface) is covered by ``test_admin_categories.py``; this file only
covers the *global* login_config endpoints.
"""

from api.routes.tests.factories import make_category, make_config
from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  PUT /login_config/notification — global update
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateLoginNotification:
    URL = "/admin/item/login_config/notification"

    def test_admin_updates_notification(self, monkeypatch, test_client):
        captured = {}

        def fake_update(data):
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"cover": {"enabled": True, "title": "Welcome"}},
        )
        assert response.status_code == 204
        assert captured["data"]["cover"]["title"] == "Welcome"

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"cover": {}},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"cover": {}},
        )
        assert response.status_code == 403

    def test_javascript_url_in_button_rejected(self, test_client):
        """Button URL with `javascript:` scheme must be rejected by
        validate_url_scheme — the route never reaches the service.
        """
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "cover": {
                    "button": {
                        "text": "Click",
                        "url": "javascript:alert(1)",
                    }
                }
            },
        )
        # validate_url_scheme raises Error("bad_request", ...) → 400.
        # If the helper internally allowed it (regression), the service
        # call would 200 instead — failing this assertion catches that.
        assert response.status_code == 400

    def test_https_url_accepted(self, monkeypatch, test_client):
        """Sanity: a clean https:// URL flows through to the service."""
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(lambda data: captured.update(data=data)),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "form": {
                    "button": {
                        "text": "Open",
                        "url": "https://example.com/info",
                    }
                }
            },
        )
        assert response.status_code == 204
        assert captured["data"]["form"]["button"]["url"] == "https://example.com/info"

    def test_button_without_url_passes(self, monkeypatch, test_client):
        """Empty/missing button.url must not trip the URL validator."""
        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"cover": {"button": {"text": "noop"}}},
        )
        assert response.status_code == 204

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(data):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.update_login_notification",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"cover": {"enabled": True}},
        )
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"


# ══════════════════════════════════════════════════════════════════════════
#  PUT /login_config/notification/cover/enable
#  PUT /login_config/notification/form/enable
# ══════════════════════════════════════════════════════════════════════════


class TestEnableLoginNotification:
    """Two near-identical handlers — pin the section name so a future
    copy-paste typo (cover/form swap) is caught.
    """

    def _stub(self, monkeypatch, captured):
        def fake_enable(section, enabled):
            captured["section"] = section
            captured["enabled"] = enabled

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.enable_login_notification",
            staticmethod(fake_enable),
        )

    def test_enable_cover(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/login_config/notification/cover/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 204
        assert captured == {"section": "cover", "enabled": True}

    def test_disable_cover(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/login_config/notification/cover/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 204
        assert captured == {"section": "cover", "enabled": False}

    def test_enable_form(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/login_config/notification/form/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 204
        assert captured == {"section": "form", "enabled": True}

    def test_missing_enabled_field_rejected(self, test_client):
        response = test_client(
            url="/admin/item/login_config/notification/cover/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={},
        )
        assert response.status_code in (400, 422)

    def test_user_forbidden(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url="/admin/item/login_config/notification/form/enable",
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"enabled": True},
        )
        assert response.status_code == 403

    def test_service_error_returns_500(self, monkeypatch, test_client):
        def boom(section, enabled):
            raise RuntimeError("write failed")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.enable_login_notification",
            staticmethod(boom),
        )
        response = test_client(
            url="/admin/item/login_config/notification/cover/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 500

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(section, enabled):
            raise Error("bad_request", "Invalid section")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminLoginConfigService.enable_login_notification",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/item/login_config/notification/cover/enable",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/login-config
#  GET /admin/login-config/{category_id}
# ══════════════════════════════════════════════════════════════════════════


class TestAdminGetLoginConfig:
    """Raw admin reads on ``manager_router`` — feed the webapp's
    "Edit login notification" modal. Backed by
    ``AdminCategoryService.admin_get_login_config(category_id=None)``.
    """

    GLOBAL_URL = "/admin/item/login-config"
    CATEGORY_URL = "/admin/item/login-config/test-cat"

    _GLOBAL_PAYLOAD = {
        "notification_cover": {"enabled": True, "title": "Hello"},
        "notification_form": {"enabled": False, "title": "Form"},
    }
    _CATEGORY_PAYLOAD = {
        "notification_cover": {"enabled": True, "title": "Cat-Cover"},
        "notification_form": {"enabled": True, "title": "Cat-Form"},
    }

    def _stub(self, monkeypatch, captured):
        def fake_get(category_id=None):
            captured["category_id"] = category_id
            return self._CATEGORY_PAYLOAD if category_id else self._GLOBAL_PAYLOAD

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminCategoryService.admin_get_login_config",
            staticmethod(fake_get),
        )

    def test_admin_reads_global(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url=self.GLOBAL_URL,
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        # No category id passed through to the service for the global read.
        assert captured["category_id"] is None
        body = response.json()
        assert body == self._GLOBAL_PAYLOAD

    def test_manager_reads_global(self, monkeypatch, test_client):
        """``manager_router`` admits managers — the modal is reachable
        from a manager-scoped admin view. Manager auth runs the
        ``maintenance(category_id)`` gate, which needs the category
        seeded in the mock DB."""
        self._stub(monkeypatch, {})
        response = test_client(
            url=self.GLOBAL_URL,
            jwt=MockJWT(role_id="manager", category_id="test-cat"),
            db_tables_data={
                "config": [make_config()],
                "categories": [make_category(id="test-cat", name="Test Cat")],
            },
        )
        assert response.status_code == 200

    def test_user_forbidden_global(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url=self.GLOBAL_URL,
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403

    def test_admin_reads_category(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url=self.CATEGORY_URL,
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        # Path id is forwarded to the service.
        assert captured["category_id"] == "test-cat"
        assert response.json() == self._CATEGORY_PAYLOAD

    def test_manager_reads_category(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url=self.CATEGORY_URL,
            jwt=MockJWT(role_id="manager", category_id="test-cat"),
            db_tables_data={
                "config": [make_config()],
                "categories": [make_category(id="test-cat", name="Test Cat")],
            },
        )
        assert response.status_code == 200

    def test_user_forbidden_category(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url=self.CATEGORY_URL,
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403

    def test_typed_error_propagates_global(self, monkeypatch, test_client):
        """``Error`` raised by the service must surface its status code,
        not be swallowed by the catch-all → 500."""

        def reject(category_id=None):
            raise Error("not_found", "no config")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminCategoryService.admin_get_login_config",
            staticmethod(reject),
        )
        response = test_client(
            url=self.GLOBAL_URL,
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 404

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(category_id=None):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminCategoryService.admin_get_login_config",
            staticmethod(boom),
        )
        response = test_client(
            url=self.GLOBAL_URL,
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"

    def test_unexpected_exception_returns_500_category(self, monkeypatch, test_client):
        def boom(category_id=None):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.login_config.AdminCategoryService.admin_get_login_config",
            staticmethod(boom),
        )
        response = test_client(
            url=self.CATEGORY_URL,
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 500
