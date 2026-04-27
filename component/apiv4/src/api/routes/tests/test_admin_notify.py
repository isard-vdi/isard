# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/notify.py — admin-triggered notifications to a user
about a desktop, to a desktop directly, and bulk notify of a hypervisor's
desktop queue. All endpoints live on admin_router.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/notify/user/desktop
# ══════════════════════════════════════════════════════════════════════════


class TestNotifyUserDesktop:
    URL = "/admin/notify/user/desktop"

    def test_admin_notifies_user(self, monkeypatch, test_client):
        captured = {}

        def fake_notify(user_id, type_, msg_code, params):
            captured["user_id"] = user_id
            captured["type"] = type_
            captured["msg_code"] = msg_code
            captured["params"] = params

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_user_desktop",
            staticmethod(fake_notify),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "user_id": "u-1",
                "type": "warning",
                "msg_code": "shutdown_imminent",
                "params": {"minutes": 10},
            },
        )
        assert response.status_code == 200
        assert captured == {
            "user_id": "u-1",
            "type": "warning",
            "msg_code": "shutdown_imminent",
            "params": {"minutes": 10},
        }

    def test_msg_code_and_params_optional(self, monkeypatch, test_client):
        """Pydantic Optional[...] = None — only user_id + type are required."""
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_user_desktop",
            staticmethod(
                lambda u, t, m, p: captured.update(user_id=u, type=t, msg=m, params=p)
            ),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"user_id": "u-1", "type": "info"},
        )
        assert response.status_code == 200
        assert captured["msg"] is None
        assert captured["params"] is None

    def test_missing_user_id_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"type": "warning"},
        )
        assert response.status_code in (400, 422)

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_user_desktop",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"user_id": "u-1", "type": "info"},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_user_desktop",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"user_id": "u-1", "type": "info"},
        )
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(*a, **k):
            raise RuntimeError("redis down")

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_user_desktop",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"user_id": "u-1", "type": "info"},
        )
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/notify/desktop
# ══════════════════════════════════════════════════════════════════════════


class TestNotifyDesktop:
    URL = "/admin/notify/desktop"

    def test_admin_notifies_desktop(self, monkeypatch, test_client):
        captured = {}

        def fake_notify(desktop_id, type_, msg_code, params):
            captured["desktop_id"] = desktop_id
            captured["type"] = type_
            captured["msg_code"] = msg_code

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop",
            staticmethod(fake_notify),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "desktop_id": "d-1",
                "type": "info",
                "msg_code": "migration_done",
            },
        )
        assert response.status_code == 200
        assert captured["desktop_id"] == "d-1"

    def test_missing_desktop_id_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"type": "info"},
        )
        assert response.status_code in (400, 422)

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(*a, **k):
            raise Error("not_found", "Desktop not found")

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"desktop_id": "ghost", "type": "info"},
        )
        assert response.status_code == 404

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"desktop_id": "d-1", "type": "info"},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/notify/desktops/queue/{hyp_id}
# ══════════════════════════════════════════════════════════════════════════


class TestNotifyDesktopQueue:
    """The handler reads the body via `await request.json()` (no Pydantic
    schema), so a non-JSON body must surface as 400 from the explicit
    `except json.JSONDecodeError` branch — not as 500.
    """

    URL = "/admin/notify/desktops/queue/hyper-1"

    def test_admin_notifies_queue(self, monkeypatch, test_client):
        captured = {}

        def fake_notify(data, hyp_id):
            captured["data"] = data
            captured["hyp_id"] = hyp_id

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop_queue",
            staticmethod(fake_notify),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue": [{"desktop_id": "d-1"}, {"desktop_id": "d-2"}]},
        )
        assert response.status_code == 200
        assert captured["hyp_id"] == "hyper-1"
        assert captured["data"]["queue"][0]["desktop_id"] == "d-1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop_queue",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"queue": []},
        )
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(data, hyp_id):
            raise Error("bad_request", "Bad queue payload")

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop_queue",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue": [{}]},
        )
        assert response.status_code == 400

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(data, hyp_id):
            raise RuntimeError("redis down")

        monkeypatch.setattr(
            "api.routes.admin.notify.AdminNotifyService.notify_desktop_queue",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue": []},
        )
        assert response.status_code == 500
