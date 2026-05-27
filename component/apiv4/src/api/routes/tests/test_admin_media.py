# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/media.py — admin/manager media listing and per-status
counts. All endpoints live on manager_router (admin + manager allowed,
user blocked). Category scoping is the service's responsibility; the
route just forwards request.token_payload.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /media/status
# ══════════════════════════════════════════════════════════════════════════


class TestGetMediaStatus:
    URL = "/admin/item/media/status"

    def test_admin_gets_status_counts(self, monkeypatch, test_client):
        captured = {}

        def fake(payload):
            captured["role_id"] = payload["role_id"]
            # ``MediaProcessed.admin_get_media_status_count`` returns
            # a list of ``{status, count}`` rows — not a status→count
            # dict. The previous stub diverged from the real shape;
            # the response_model now enforces it.
            return [
                {"status": "Downloaded", "count": 5},
                {"status": "Failed", "count": 1},
            ]

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media_status",
            staticmethod(fake),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        downloaded = next(row for row in body if row["status"] == "Downloaded")
        assert downloaded["count"] == 5
        assert captured["role_id"] == "admin"

    def test_manager_gets_status_counts(self, monkeypatch, test_client):
        """Manager_router endpoint — managers must succeed; service
        is responsible for scoping to their category."""
        captured = {}

        def fake(payload):
            captured["role_id"] = payload["role_id"]
            captured["category_id"] = payload["category_id"]
            return [{"status": "Downloaded", "count": 1}]

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media_status",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            jwt=MockJWT(role_id="manager", category_id="default"),
        )
        assert response.status_code == 200
        assert captured == {"role_id": "manager", "category_id": "default"}

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media_status",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(payload):
            raise RuntimeError("DB down")

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media_status",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/media
# ══════════════════════════════════════════════════════════════════════════


class TestListAllMedia:
    URL = "/admin/items/media"

    def test_admin_lists_media(self, monkeypatch, test_client):
        captured = {}

        def fake(payload):
            captured["role_id"] = payload["role_id"]
            return [{"id": "m1", "name": "Ubuntu ISO"}]

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(fake),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "m1"

    def test_manager_allowed(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 200

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def fail(payload):
            raise Error("forbidden", "Category disabled")

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(fail),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/media/{status}
# ══════════════════════════════════════════════════════════════════════════


class TestListMediaByStatus:
    def test_status_passed_as_kwarg(self, monkeypatch, test_client):
        """The route extracts the path param into a status kwarg —
        the service must NOT receive it positionally so a future
        get_media(payload, *, status=None) signature change keeps
        working."""
        captured = {}

        def fake(payload, status=None):
            captured["status"] = status
            return [{"id": "m1"}]

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/items/media/Downloaded", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["status"] == "Downloaded"

    def test_manager_allowed(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(lambda payload, status=None: []),
        )
        response = test_client(
            url="/admin/items/media/Downloaded", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 200

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(lambda payload, status=None: []),
        )
        response = test_client(
            url="/admin/items/media/Downloaded", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_unknown_status_propagates_typed_error(self, monkeypatch, test_client):
        """The route doesn't validate the status path param — the
        service does. If it raises Error("bad_request", ...), the
        admin sees 400, not 500."""

        def reject(payload, status=None):
            raise Error("bad_request", f"Unknown status: {status}")

        monkeypatch.setattr(
            "api.routes.admin.media.AdminMediaService.get_media",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/items/media/no_such_status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 400
