# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/notifications.py — notification templates, notification
CRUD, notification data (status/grouped/delete), and admin user displays.

The file also declares user-facing token_router endpoints (/notifications/
status-bar, /notification/user/displays/{trigger}, etc.), but those URLs
are already claimed by routes/notifications.py (registered first), so
the admin-side copies are dead code. Coverage of the live endpoints
lives in test_notifications.py; the dead-code handlers should be deleted
in a follow-up cleanup PR.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  Notification templates (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestTemplateCreate:
    URL = "/admin/notifications/template"

    def _payload(self, **overrides):
        body = {
            "language": "en",
            "title": "Hello",
            "body": "<p>welcome</p>",
            "footer": "",
            "name": "welcome-tmpl",
        }
        body.update(overrides)
        return body

    def test_admin_creates(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.create_template",
            staticmethod(lambda data: captured.update(data=data)),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert captured["data"]["language"] == "en"

    def test_missing_required_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"language": "en"},  # title/body/footer missing
        )
        assert response.status_code in (400, 422)

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.create_template",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403


class TestTemplateList:
    """Three list endpoints share the same handler shape but pass different
    `kind` arguments to the service. Pin each one's argument so a future
    copy-paste typo (kind="custom" vs kind="system") is caught.
    """

    def _stub(self, monkeypatch, captured):
        def fake_get(kind=None):
            captured["kind"] = kind
            return [{"id": "t1"}]

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_templates",
            staticmethod(fake_get),
        )

    def test_all_templates(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/notifications/templates", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        # The all-templates handler calls `get_templates()` with no arg.
        assert captured["kind"] is None
        assert response.json()["templates"][0]["id"] == "t1"

    def test_custom_templates(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/notifications/templates/custom",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["kind"] == "custom"

    def test_system_templates(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/notifications/templates/system",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["kind"] == "system"

    def test_user_forbidden(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url="/admin/notifications/templates", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


class TestTemplateGet:
    URL = "/admin/notifications/template/t-123"

    def test_admin_gets_template(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_template",
            staticmethod(lambda tid: {"id": tid, "name": "Welcome"}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["id"] == "t-123"

    def test_unknown_template_returns_404(self, monkeypatch, test_client):
        def not_found(tid):
            raise Error("not_found", "Template not found")

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_template",
            staticmethod(not_found),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 404


class TestTemplatePreview:
    URL = "/admin/notifications/template/preview"

    def test_admin_previews(self, monkeypatch, test_client):
        captured = {}

        def fake_preview(event, user_id, data):
            captured["event"] = event
            captured["user_id"] = user_id
            captured["data"] = data
            return {"title": "rendered", "body": "ok"}

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.preview_template",
            staticmethod(fake_preview),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "event": "shutdown",
                "user_id": "u-1",
                "data": {"reason": "maintenance"},
            },
        )
        assert response.status_code == 200
        assert captured == {
            "event": "shutdown",
            "user_id": "u-1",
            "data": {"reason": "maintenance"},
        }
        assert response.json()["title"] == "rendered"

    def test_data_optional(self, monkeypatch, test_client):
        """data has a default of {} — sending only event must work."""
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.preview_template",
            staticmethod(lambda e, u, d: {"title": "ok"}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"event": "shutdown"},
        )
        assert response.status_code == 200

    def test_missing_event_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"data": {}},
        )
        assert response.status_code in (400, 422)


class TestTemplateUpdate:
    URL = "/admin/notifications/template/t-123"

    def test_admin_updates(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.update_template",
            staticmethod(lambda tid, data: captured.update(template_id=tid, data=data)),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "language": "en",
                "title": "Updated",
                "body": "<p>new</p>",
                "footer": "",
            },
        )
        assert response.status_code == 200
        assert captured["template_id"] == "t-123"
        assert captured["data"]["title"] == "Updated"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.update_template",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"language": "en", "title": "x", "body": "x", "footer": ""},
        )
        assert response.status_code == 403


class TestTemplateDelete:
    URL = "/admin/notifications/template/t-123"

    def test_admin_deletes(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_template",
            staticmethod(lambda tid: captured.update(template_id=tid)),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["template_id"] == "t-123"
        assert response.json()["message_code"] == "item.deleted"

    def test_template_in_use_returns_400(self, monkeypatch, test_client):
        def reject(tid):
            raise Error("bad_request", "Template is in use")

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_template",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
#  Notifications CRUD (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestNotificationCRUD:
    LIST_URL = "/admin/notifications"
    CREATE_URL = "/admin/notification"

    def test_list(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_all_notifications",
            staticmethod(lambda: [{"id": "n1"}]),
        )
        response = test_client(url=self.LIST_URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["notifications"][0]["id"] == "n1"

    def test_create_returns_id(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.create_notification",
            staticmethod(lambda data: "new-n-1"),
        )
        response = test_client(
            url=self.CREATE_URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"name": "myn", "trigger": "login"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == "new-n-1"

    def test_get_one(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notification",
            staticmethod(lambda nid: {"id": nid, "name": "myn", "ignore_after": None}),
        )
        response = test_client(
            url="/admin/notification/n-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        # NotificationDetailResponse is a RootModel — body is the row itself.
        assert response.json()["id"] == "n-1"

    def test_get_one_not_found(self, monkeypatch, test_client):
        def not_found(nid):
            raise Error("not_found", "Notification not found")

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notification",
            staticmethod(not_found),
        )
        response = test_client(
            url="/admin/notification/ghost", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_update(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.update_notification",
            staticmethod(lambda nid, data: captured.update(nid=nid, data=data)),
        )
        response = test_client(
            url="/admin/notification/n-1",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"name": "renamed"},
        )
        assert response.status_code == 200
        assert captured["nid"] == "n-1"
        # exclude_none drops the unset fields
        assert captured["data"] == {"name": "renamed"}

    def test_delete_with_logs(self, monkeypatch, test_client):
        captured = {}

        def fake_delete(nid, delete_logs):
            captured["nid"] = nid
            captured["delete_logs"] = delete_logs

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_notification",
            staticmethod(fake_delete),
        )
        response = test_client(
            url="/admin/notification/n-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
            body={"delete_logs": False},
        )
        assert response.status_code == 200
        assert captured == {"nid": "n-1", "delete_logs": False}

    def test_user_forbidden_on_create(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.create_notification",
            staticmethod(lambda data: ""),
        )
        response = test_client(
            url=self.CREATE_URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"name": "x"},
        )
        assert response.status_code == 403


class TestNotificationActions:
    URL = "/admin/notification/actions"

    def test_list_actions(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notification_actions",
            staticmethod(lambda: [{"id": "a1", "label": "ack"}]),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["actions"][0]["id"] == "a1"


# ══════════════════════════════════════════════════════════════════════════
#  Notification data (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestNotificationData:
    def test_get_by_status_user(self, monkeypatch, test_client):
        captured = {}

        def fake(status, user_id):
            captured["status"] = status
            captured["user_id"] = user_id
            return [{"id": "nd1"}]

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notifications_data_by_status",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/notifications/data/status/pending/user/u-1",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured == {"status": "pending", "user_id": "u-1"}
        assert response.json()["data"][0]["id"] == "nd1"

    def test_statuses(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notification_statuses",
            staticmethod(lambda: ["pending", "ack"]),
        )
        response = test_client(
            url="/admin/notifications/statuses", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["statuses"] == ["pending", "ack"]

    def test_grouped_by_status(self, monkeypatch, test_client):
        captured = {}

        def fake(status):
            captured["status"] = status
            return [{"user_id": "u1", "count": 3}]

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_notifications_grouped_by_status",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/notifications/data/by_status/pending",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured == {"status": "pending"}

    def test_delete_user_data(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_user_notification_data",
            staticmethod(lambda uid: captured.update(user_id=uid)),
        )
        response = test_client(
            url="/admin/notifications/data/user/u-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["user_id"] == "u-1"

    def test_delete_specific_data(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_notification_data",
            staticmethod(lambda nid: captured.update(nid=nid)),
        )
        response = test_client(
            url="/admin/notifications/data/nd-99",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["nid"] == "nd-99"

    def test_delete_all_data(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_all_notification_data",
            staticmethod(lambda: called.update(yes=True)),
        )
        response = test_client(
            url="/admin/notifications/data",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert called["yes"] is True

    def test_user_forbidden_on_delete_all(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.delete_all_notification_data",
            staticmethod(lambda: None),
        )
        response = test_client(
            url="/admin/notifications/data",
            method="DELETE",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  User displays (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestAdminUserDisplays:
    def test_admin_gets_displays(self, monkeypatch, test_client):
        captured = {}

        def fake(user_id, trigger):
            captured["user_id"] = user_id
            captured["trigger"] = trigger
            return ["modal", "banner"]

        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_user_displays",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/notifications/user/displays/u-1/login",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert response.json()["displays"] == ["modal", "banner"]
        assert captured == {"user_id": "u-1", "trigger": "login"}

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.notifications.AdminNotificationService.get_user_displays",
            staticmethod(lambda uid, trig: []),
        )
        response = test_client(
            url="/admin/notifications/user/displays/u-1/login",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  User-facing endpoints (token_router)
#
#  NOTE — admin/notifications.py also declares user-facing routes
#    GET /notifications/status-bar
#    GET /notification/user/displays/{trigger}
#    GET /notification/user/{trigger}/{display}
#    DELETE /notifications/expired
#  but those URLs are ALREADY claimed by routes/notifications.py
#  (imported earlier in api/__init__.py — first registration wins on
#  the same router). Coverage for the live endpoints lives in
#  test_notifications.py; the admin/notifications.py copies are dead
#  code and should be deleted in a follow-up cleanup PR.
# ══════════════════════════════════════════════════════════════════════════
