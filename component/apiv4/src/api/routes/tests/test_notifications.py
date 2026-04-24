import pytest
from api.routes.tests.factories import make_config, make_user
from api.routes.tests.helpers import MockJWT


@pytest.fixture()
def notifications_db_factory():
    """Fixture to create a mock database for notification tests."""

    def notifications_db_tables_data(jwt: MockJWT):
        p = jwt.payload
        return {
            "config": [
                make_config(
                    auth={
                        "local": {
                            "active": True,
                            "error_messages": {
                                "invalid_credentials": None,
                                "rate_limit": None,
                                "unknown": None,
                                "user_disabled": None,
                                "user_disallowed": None,
                            },
                            "migration": {
                                "action_after_migrate": "none",
                                "export": False,
                                "force_migration": False,
                                "import": True,
                                "notification_bar": {
                                    "enabled": False,
                                    "level": "info",
                                    "template": "00000000-00000000-00000000-00000000",
                                },
                            },
                        },
                    }
                )
            ],
            "notification_tmpls": [
                {
                    "default": "es",
                    "description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
                    "id": "00000000-00000000-00000000-00000000",
                    "kind": "generic_notice",
                    "lang": {
                        "en": {
                            "body": "<p>Message in English <b>{name}</b> at <b>{accessed}</b>.</p>",
                            "footer": "Footer message.",
                            "title": "Title",
                        },
                    },
                    "name": "Generic notice",
                    "system": {
                        "body": "<p>Message in system language (english) <b>{name}</b> at <b>{accessed}</b>.</p>",
                        "footer": "Footer message.",
                        "title": "Title",
                    },
                    "vars": {
                        "accessed": "12 Mar 2024 13:00",
                        "name": "Testing environment",
                    },
                }
            ],
            "users": [
                make_user(jwt=jwt, role_id=p["role_id"]),
                make_user(
                    id="another-user",
                    name="Another User",
                    username="another-user",
                    uid="another-user",
                    role="advanced",  # note: field is "role" not "role_id"
                    role_id="advanced",
                    provider="local",
                    group=p["group_id"],
                    category=p["category_id"],
                ),
            ],
        }

    return notifications_db_tables_data


def test_get_status_bar(monkeypatch, test_client):
    """GET /notifications/status-bar — wires to
    ``AdminNotificationsService.get_status_bar_notification`` which
    mirrors v3 ``api_v3_get_status_bar_notifications``. Returns
    ``None`` when the status-bar template is disabled or neither
    migration direction is enabled for the caller's provider.
    Replaces the previous mock route at ``/items/notification/status-bar``
    which always returned ``None`` regardless of configuration.
    """
    jwt = MockJWT()
    captured = {}

    def fake_get_status_bar(payload):
        captured["user_id"] = payload["user_id"]
        return None

    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService."
        "get_status_bar_notification",
        staticmethod(fake_get_status_bar),
    )

    response = test_client(
        method="GET",
        url="/notifications/status-bar",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() is None
    assert captured == {"user_id": jwt.payload["user_id"]}


# ─── Admin notification routes (T1 shim replacements) ───────────────────


def test_admin_get_notification_template(monkeypatch, test_client):
    """GET /admin/notifications/template/{id} — replaces v3
    /message-template/{id} shim."""
    jwt = MockJWT()
    stub = {
        "id": "tmpl-1",
        "name": "Email template",
        "body": "Hello {{name}}",
    }
    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService.get_template",
        staticmethod(lambda template_id: stub),
    )

    response = test_client(url="/admin/notifications/template/tmpl-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_list_notification_actions(monkeypatch, test_client):
    """GET /admin/notification/actions — replaces
    /admin/notification/actions/all v3 shim. NotificationActionsResponse
    wraps ``actions: list[dict]`` so the stub must return dicts."""
    jwt = MockJWT()
    stub = [
        {"id": "send_email", "name": "Send email"},
        {"id": "log", "name": "Log event"},
    ]
    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService.get_notification_actions",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/notification/actions", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"actions": stub}


def test_admin_create_notification_template(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(data):
        captured["language"] = data["language"]
        captured["title"] = data["title"]

    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService.create_template",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/notifications/template",
        method="POST",
        body={
            "language": "en",
            "title": "Welcome",
            "body": "Hello {{name}}",
            "footer": "Kind regards",
            "name": "welcome",
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"language": "en", "title": "Welcome"}


def test_admin_list_notification_templates(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "tmpl-1", "name": "welcome"}]
    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService.get_templates",
        staticmethod(lambda kind=None: stub),
    )

    response = test_client(url="/admin/notifications/templates", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"templates": stub}


def test_admin_delete_notification_template(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin_notifications.AdminNotificationService.delete_template",
        staticmethod(lambda template_id: calls.append(template_id)),
    )

    response = test_client(
        url="/admin/notifications/template/tmpl-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["tmpl-1"]


# ─── User trigger/display notification routes (nested + flat variants) ──


def test_get_user_notification_trigger_display_nested(monkeypatch, test_client):
    """GET /notification/user/{trigger}/{display} — nested-shape endpoint
    that mirrors legacy v3 ``api_v3_get_user_notifications`` so Vue 2 and
    webapp callers keep working after the v3 retirement. The response is
    the raw ``{order: {item_type: NotificationUserData}}`` grouping
    emitted by ``NotificationsProcessed.get_user_trigger_notifications``.
    """
    jwt = MockJWT()
    captured = {}
    stub = {
        1: {
            "desktop": {
                "display": ["modal"],
                "action_id": "accept",
                "template_id": "00000000-00000000-00000000-00000000",
                "force_accept": False,
                "notifications": [
                    {"id": "n-1", "title": "Hi", "body": "Hello", "vars": {}}
                ],
                "template": {
                    "title": "Welcome",
                    "body": "Body",
                    "footer": "Footer",
                },
            }
        }
    }

    def fake_get(payload, trigger, display):
        captured["user_id"] = payload["user_id"]
        captured["trigger"] = trigger
        captured["display"] = display
        return stub

    monkeypatch.setattr(
        "api.services.notifications.NotificationService.get_user_trigger_notifications",
        staticmethod(fake_get),
    )

    response = test_client(
        method="GET",
        url="/notification/user/start_desktop/modal",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert "notifications" in body
    assert "1" in body["notifications"]
    assert "desktop" in body["notifications"]["1"]
    assert body["notifications"]["1"]["desktop"]["action_id"] == "accept"
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "trigger": "start_desktop",
        "display": "modal",
    }


def test_get_user_notification_trigger_display_nested_empty(monkeypatch, test_client):
    """GET /notification/user/{trigger}/{display} returns an empty
    ``notifications`` object when the service finds no matching
    templates for the caller's trigger/display combination."""
    jwt = MockJWT()

    monkeypatch.setattr(
        "api.services.notifications.NotificationService.get_user_trigger_notifications",
        staticmethod(lambda payload, trigger, display: {}),
    )

    response = test_client(
        method="GET",
        url="/notification/user/start_desktop/modal",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"notifications": {}}
