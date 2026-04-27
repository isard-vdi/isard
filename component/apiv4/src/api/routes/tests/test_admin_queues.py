# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/queues.py — RQ queue introspection (jobs by status,
consumer/worker list) plus the auto-delete-old-tasks lifecycle (config,
list, manual delete, auto delete, enable toggle, retention/registry
config). All endpoints sit on admin_router (admin-only).
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/queues, /admin/queues/consumers
# ══════════════════════════════════════════════════════════════════════════


class TestListing:
    def test_queues(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: [{"id": "default", "queued": 3}]),
        )
        response = test_client(url="/admin/queues", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "default"

    def test_consumers(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_consumers",
            staticmethod(lambda: [{"id": "w-1", "queue": "default"}]),
        )
        response = test_client(
            url="/admin/queues/consumers", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()[0]["id"] == "w-1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: []),
        )
        response = test_client(url="/admin/queues", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_queues",
            staticmethod(lambda: []),
        )
        response = test_client(url="/admin/queues", jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/queues/old_tasks/config  AND  /admin/queues/old_tasks/{older_than}
# ══════════════════════════════════════════════════════════════════════════


class TestOldTasksRead:
    def test_config_returns_state(self, monkeypatch, test_client):
        """The /config endpoint MUST be declared before the
        /{older_than} catch-all — otherwise FastAPI tries to coerce
        "config" to an int and 422s. The fact that this test passes
        with status 200 (and does not 422 on parsing) is the regression
        guard.
        """
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_auto_delete_config",
            staticmethod(
                lambda: {"older_than": 86400, "queue_registries": [], "enabled": True}
            ),
        )
        response = test_client(
            url="/admin/queues/old_tasks/config",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    def test_older_than_path_param(self, monkeypatch, test_client):
        captured = {}

        def fake(older_than):
            captured["older_than"] = older_than
            return [{"id": "t-1"}]

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.get_old_tasks",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/queues/old_tasks/86400",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        # The Path param is typed `int` — pin that the coercion happens.
        assert captured["older_than"] == 86400
        assert isinstance(captured["older_than"], int)

    def test_non_int_older_than_rejected(self, test_client):
        response = test_client(
            url="/admin/queues/old_tasks/not-a-number",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/queues/old_tasks  (manual)
# ══════════════════════════════════════════════════════════════════════════


class TestManualDeleteOldTasks:
    URL = "/admin/queues/old_tasks"

    def test_admin_deletes(self, monkeypatch, test_client):
        captured = {}

        def fake(older_than):
            captured["older_than"] = older_than
            return {"ok": ["t-1"], "errors": []}

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
            body={"older_than": 86400},
        )
        assert response.status_code == 200
        assert captured["older_than"] == 86400
        assert response.json()["ok"] == ["t-1"]

    def test_zero_older_than_returns_400(self, monkeypatch, test_client):
        """The handler explicitly rejects falsy older_than (zero) with
        a typed bad_request — even though the Pydantic schema accepts
        0 as a valid int. This guards against a no-op request that
        would otherwise wipe nothing silently.
        """

        # Service must NOT be called for 0.
        def should_not_run(older_than):
            raise AssertionError("delete_old_tasks called with older_than=0")

        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(should_not_run),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
            body={"older_than": 0},
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks",
            staticmethod(lambda older_than: {}),
        )
        response = test_client(
            url=self.URL,
            method="DELETE",
            jwt=MockJWT(role_id="user"),
            body={"older_than": 86400},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/max_time/{max_time}
# ══════════════════════════════════════════════════════════════════════════


class TestSetMaxTime:
    def test_admin_sets_max_time(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_max_time",
            staticmethod(lambda mt: captured.update(max_time=mt) or {"older_than": mt}),
        )
        response = test_client(
            url="/admin/queues/old_tasks/config/max_time/172800",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["max_time"] == 172800
        assert isinstance(captured["max_time"], int)


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/queue_registries
# ══════════════════════════════════════════════════════════════════════════


class TestSetQueueRegistries:
    URL = "/admin/queues/old_tasks/config/queue_registries"

    def test_admin_sets_registries(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_queue_registries",
            staticmethod(lambda regs: captured.update(regs=regs) or {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue_registries": ["failed", "finished"]},
        )
        assert response.status_code == 200
        assert captured["regs"] == ["failed", "finished"]

    def test_null_registries_passes_empty_list(self, monkeypatch, test_client):
        """Schema default is [] but the handler reads `data.queue_registries
        or []` so explicit null (None) also coerces to []."""
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_queue_registries",
            staticmethod(lambda regs: captured.update(regs=regs) or {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"queue_registries": None},
        )
        assert response.status_code == 200
        assert captured["regs"] == []


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/queues/old_tasks/config/enabled
# ══════════════════════════════════════════════════════════════════════════


class TestSetEnabled:
    URL = "/admin/queues/old_tasks/config/enabled"

    def test_enable(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_auto_delete_enabled",
            staticmethod(
                lambda enabled: captured.update(enabled=enabled) or {"enabled": enabled}
            ),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": True},
        )
        assert response.status_code == 200
        assert captured["enabled"] is True

    def test_disable(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.set_auto_delete_enabled",
            staticmethod(lambda enabled: captured.update(enabled=enabled) or {}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"enabled": False},
        )
        assert response.status_code == 200
        assert captured["enabled"] is False

    def test_missing_enabled_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={},
        )
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/queues/old_tasks/auto
# ══════════════════════════════════════════════════════════════════════════


class TestAutoDelete:
    URL = "/admin/queues/old_tasks/auto"

    def test_admin_runs_auto_delete(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks_auto",
            staticmethod(
                lambda: called.update(yes=True) or {"ok": ["t-1"], "errors": []}
            ),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert called["yes"] is True
        assert response.json()["ok"] == ["t-1"]

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.queues.AdminQueuesService.delete_old_tasks_auto",
            staticmethod(lambda: {}),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403
