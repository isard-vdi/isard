# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/backups.py — backup listing, single-backup get, backup
config, and the backupninja report submission endpoint.

The route file relies on declaration order:
    /admin/backups/config        MUST come before
    /admin/backups/{backup_id}
otherwise the catch-all wins and "config" gets parsed as a backup_id.
A regression here would make /admin/backups/config silently 404.
The TestBackupConfig.test_returns_config_not_404 test pins this.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/backups   (list-or-by-id via query param)
# ══════════════════════════════════════════════════════════════════════════


class TestListBackups:
    URL = "/admin/backups"

    def test_admin_lists_all(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(lambda: [{"id": "b1"}, {"id": "b2"}]),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_id_query_param_routes_to_get_backup(self, monkeypatch, test_client):
        """When the caller passes ?id=..., the handler must call
        get_backup(id, pluck=...) instead of list_backups(). The pluck
        param is forwarded as-is so the caller can narrow the response.
        """
        captured = {}

        def fake_get(backup_id, pluck=None):
            captured["backup_id"] = backup_id
            captured["pluck"] = pluck
            return {"id": backup_id, "status": "ok"}

        def list_should_not_run():
            raise AssertionError("list_backups must not be called when ?id= is set")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(fake_get),
        )
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(list_should_not_run),
        )
        response = test_client(
            url=f"{self.URL}?id=b-99&pluck=status",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured == {"backup_id": "b-99", "pluck": "status"}

    def test_id_without_pluck_passes_none(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(
                lambda backup_id, pluck=None: captured.update(
                    backup_id=backup_id, pluck=pluck
                )
                or {}
            ),
        )
        response = test_client(url=f"{self.URL}?id=b-1", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["pluck"] is None

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def fail(_=None, pluck=None):
            raise Error("not_found", "Backup b-99 not found")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(fail),
        )
        response = test_client(url=f"{self.URL}?id=b-99", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 404

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/backups/config
# ══════════════════════════════════════════════════════════════════════════


class TestBackupConfig:
    URL = "/admin/backups/config"

    def test_returns_config_not_404(self, monkeypatch, test_client):
        """Route declaration order safety: /admin/backups/config must
        match before /admin/backups/{backup_id}. If a future refactor
        flips the order, FastAPI matches `config` as a backup_id and
        get_backup("config") raises Error("not_found") → this test
        sees 404 instead of 200 and fails.
        """
        called_get_backup = {}

        def fake_get_backup(backup_id, pluck=None):
            called_get_backup["yes"] = backup_id
            raise Error("not_found", "Backup config not found")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(fake_get_backup),
        )
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup_config",
            staticmethod(lambda: {"path": "/var/backups", "retention_days": 30}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["retention_days"] == 30
        assert "yes" not in called_get_backup, (
            "/admin/backups/config matched the {backup_id} catch-all — "
            "declaration order regression in admin/backups.py"
        )

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup_config",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("env vars missing")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup_config",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/backups/{backup_id}
# ══════════════════════════════════════════════════════════════════════════


class TestGetBackup:
    URL = "/admin/backups/b-123"

    def test_admin_gets_backup(self, monkeypatch, test_client):
        captured = {}

        def fake_get(backup_id):
            captured["backup_id"] = backup_id
            return {"id": backup_id, "status": "ok"}

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["backup_id"] == "b-123"

    def test_unknown_backup_returns_404(self, monkeypatch, test_client):
        def fail(backup_id):
            raise Error("not_found", "Backup not found")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(fail),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 404

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup",
            staticmethod(lambda b: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /backups   (admin_router) — backupninja report submission
# ══════════════════════════════════════════════════════════════════════════


class TestBackupReport:
    URL = "/backups"

    def _payload(self, **overrides):
        body = {
            "timestamp": "2026-04-27T12:00:00",
            "status": "ok",
            "type": "automated",
            "scope": "full",
        }
        body.update(overrides)
        return body

    def test_admin_submits_report(self, monkeypatch, test_client):
        captured = {}

        def fake_insert(data):
            captured["data"] = data
            return {"id": "report-1"}

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.insert_backup",
            staticmethod(fake_insert),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(details={"checks": []}),
        )
        assert response.status_code == 200
        assert captured["data"]["status"] == "ok"
        assert captured["data"]["details"] == {"checks": []}

    def test_missing_required_field_rejected(self, test_client):
        """status / type / scope / timestamp are required (Field(...))."""
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"status": "ok"},
        )
        assert response.status_code in (400, 422)

    def test_unexpected_exception_returns_400(self, monkeypatch, test_client):
        """The handler's generic except branch wraps non-Error exceptions
        as bad_request (NOT internal_server) — backupninja runs this
        endpoint with externally-supplied data, so a parse failure is
        a client error, not a server crash. Pin that contract.
        """

        def boom(data):
            raise RuntimeError("Unparseable details payload")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.insert_backup",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.insert_backup",
            staticmethod(lambda data: {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.insert_backup",
            staticmethod(lambda data: {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=self._payload(),
        )
        assert response.status_code == 403
