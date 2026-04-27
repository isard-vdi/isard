# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/viewers_config.py — get-all, per-viewer update, per-viewer
reset. All endpoints live on admin_router (admin-only).
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/viewers-config
# ══════════════════════════════════════════════════════════════════════════


class TestGetViewersConfig:
    URL = "/admin/viewers-config"

    def test_admin_gets_config(self, monkeypatch, test_client):
        sample = {
            "file_spice": {"custom": "title=spice"},
            "file_rdpgw": {"custom": "screen mode id:i:2"},
        }
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.get_viewers_config",
            staticmethod(lambda: sample),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["file_spice"]["custom"] == "title=spice"

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.get_viewers_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.get_viewers_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.get_viewers_config",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/viewers-config/{viewer}
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateViewerConfig:
    URL = "/admin/viewers-config/file_spice"

    def test_admin_updates_config(self, monkeypatch, test_client):
        captured = {}

        def fake_update(viewer, custom):
            captured["viewer"] = viewer
            captured["custom"] = custom

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.update_viewers_config",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"custom": "title=spice-updated"},
        )
        assert response.status_code == 200
        assert captured == {"viewer": "file_spice", "custom": "title=spice-updated"}

    def test_admin_clears_custom_with_null(self, monkeypatch, test_client):
        """Sending custom=null must reach the service as None so the
        custom config is cleared, not stored as the literal string "null"."""
        captured = {}

        def fake_update(viewer, custom):
            captured["custom"] = custom

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.update_viewers_config",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"custom": None},
        )
        assert response.status_code == 200
        assert captured["custom"] is None

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.update_viewers_config",
            staticmethod(lambda v, c: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"custom": "x"},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.update_viewers_config",
            staticmethod(lambda v, c: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"custom": "x"},
        )
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(viewer, custom):
            raise Error("not_found", "Unknown viewer")

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.update_viewers_config",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"custom": "x"},
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/viewers-config/reset/{viewer}
# ══════════════════════════════════════════════════════════════════════════


class TestResetViewerConfig:
    def test_admin_resets_known_viewer(self, monkeypatch, test_client):
        captured = {}

        def fake_reset(viewer):
            captured["viewer"] = viewer

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.reset_viewers_config",
            staticmethod(fake_reset),
        )
        response = test_client(
            url="/admin/viewers-config/reset/file_spice",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["viewer"] == "file_spice"

    def test_unknown_viewer_returns_400(self, monkeypatch, test_client):
        """Per the route summary: only file_rdpgw / file_rdpvpn / file_spice
        are valid; the service raises Error("bad_request") for anything else.
        """

        def reject(viewer):
            raise Error("bad_request", "Invalid viewer")

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.reset_viewers_config",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/viewers-config/reset/file_unknown",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.reset_viewers_config",
            staticmethod(lambda v: None),
        )
        response = test_client(
            url="/admin/viewers-config/reset/file_spice",
            method="PUT",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(viewer):
            raise RuntimeError("write failed")

        monkeypatch.setattr(
            "api.routes.admin.viewers_config.AdminViewersConfigService.reset_viewers_config",
            staticmethod(boom),
        )
        response = test_client(
            url="/admin/viewers-config/reset/file_spice",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 500
