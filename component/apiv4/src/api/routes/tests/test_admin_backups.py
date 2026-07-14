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
    URL = "/admin/items/backups"

    def test_admin_lists_all(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(lambda limit=None: [{"id": "b1"}, {"id": "b2"}]),
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
            staticmethod(lambda limit=None: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.list_backups",
            staticmethod(lambda limit=None: []),
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
    URL = "/admin/item/backups/config"

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
        # Real ``AdminBackupsService.get_backup_config`` returns the
        # ``{schedule, enabled, main_schedule_hour}`` shape now pinned by
        # ``BackupConfigResponse``; the previous stub returned a fictional
        # ``{path, retention_days}`` blob the schema would reject.
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_backup_config",
            staticmethod(
                lambda: {
                    "schedule": {
                        "db": 19,
                        "redis": None,
                        "stats": None,
                        "config": None,
                        "disks": None,
                    },
                    "enabled": {
                        "db": True,
                        "redis": False,
                        "stats": False,
                        "config": False,
                        "disks": False,
                    },
                    "main_schedule_hour": 19,
                }
            ),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["main_schedule_hour"] == 19
        assert "yes" not in called_get_backup, (
            "/admin/item/backups/config matched the {backup_id} catch-all — "
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
    URL = "/admin/item/backups/b-123"

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
    URL = "/admin/item/backups"

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
            # Real ``AdminBackupsService.insert_backup`` returns the
            # ``{id, status, message}`` shape; ``BackupReportInsertResponse``
            # enforces that.
            return {
                "id": "report-1",
                "status": "success",
                "message": "Backup record created successfully",
            }

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

    def test_report_extra_fields_reach_service(self, monkeypatch, test_client):
        """The parser emits rich fields that are not declared on the schema
        (disk_types, actions, the *_actions counts, duration,
        backup_types_status, ...). ``BackupReportRequest`` is
        ``extra="allow"`` so they survive validation and reach the service —
        otherwise pydantic drops them and the webapp backups view renders
        empty action/duration/per-type columns.
        """
        captured = {}

        def fake_insert(data):
            captured["data"] = data
            return {"id": "r-1", "status": "success", "message": "ok"}

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.insert_backup",
            staticmethod(fake_insert),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(
                disk_types=["qcow2", "raw"],
                total_actions=5,
                successful_actions=5,
                warning_actions=0,
                failed_actions=0,
                duration=42,
                backup_types_status={"db": "success", "redis": "not_included"},
            ),
        )
        assert response.status_code == 200
        data = captured["data"]
        assert data["disk_types"] == ["qcow2", "raw"]
        assert data["total_actions"] == 5
        assert data["duration"] == 42
        assert data["backup_types_status"] == {
            "db": "success",
            "redis": "not_included",
        }

    def test_report_id_cannot_be_forced_by_caller(self, monkeypatch, test_client):
        """``id`` (and the server timestamps) are server-owned. Even though the
        schema is ``extra="allow"``, a caller-supplied ``id`` must be stripped
        before insert — otherwise it becomes the RethinkDB primary key, the
        insert result has no ``generated_keys``, and the endpoint 500s while the
        row is written (poisoning the backupninja retry queue).
        """
        captured = {}

        def fake_insert(data):
            captured["data"] = dict(data)
            # Mirror the DAL: a real (auto-PK) insert returns generated_keys.
            return {"inserted": 1, "generated_keys": ["server-generated"]}

        # Patch the DAL where the service module bound it, and stub the
        # retention sweep so the real insert_backup runs without a DB.
        monkeypatch.setattr(
            "api.services.admin.backups.BackupsProcessed.insert",
            staticmethod(fake_insert),
        )
        monkeypatch.setattr(
            "api.services.admin.backups.AdminBackupsService._cleanup_old_backups",
            staticmethod(lambda: 0),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(id="attacker-chosen", received_at="x", created_at="y"),
        )
        assert response.status_code == 200
        assert "id" not in captured["data"]
        assert "received_at" not in captured["data"]
        assert "created_at" not in captured["data"]
        assert response.json()["id"] == "server-generated"

    def test_missing_required_field_rejected(self, test_client):
        """status / type / scope / timestamp are required (Field(...))."""
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"status": "ok"},
        )
        assert response.status_code in (400, 422)

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        """The handler's generic except branch surfaces non-Error
        exceptions as internal_server (500). Main commit 803e4392f
        explicitly dropped the blanket-except that turned every server
        error into a 400 — backupninja's data is service-token gated and
        Pydantic validates the request body, so anything that still
        reaches the except branch is a real server fault.
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
        assert response.status_code == 500

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


# ══════════════════════════════════════════════════════════════════════════
#  GET/PUT /admin/backups/integrity   (saturday borg-check toggle)
# ══════════════════════════════════════════════════════════════════════════


class TestBackupIntegrityToggle:
    URL = "/admin/item/backups/integrity"

    def test_admin_gets_toggle_disabled_default(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_integrity_enabled",
            staticmethod(lambda: False),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"integrity_enabled": False}

    def test_admin_gets_toggle_enabled(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_integrity_enabled",
            staticmethod(lambda: True),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"integrity_enabled": True}

    def test_user_forbidden_get(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.get_integrity_enabled",
            staticmethod(lambda: False),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_admin_sets_toggle(self, monkeypatch, test_client):
        captured = {}

        def fake_set(value):
            captured["value"] = value
            return {"integrity_enabled": value}

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.set_integrity_enabled",
            staticmethod(fake_set),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"integrity_enabled": True},
        )
        assert response.status_code == 200
        assert captured["value"] is True
        assert response.json() == {"integrity_enabled": True}

    def test_set_rejects_non_bool(self, monkeypatch, test_client):
        """Pydantic body validation must reject non-boolean values
        before the service is invoked."""

        def should_not_run(value):
            raise AssertionError("Service must not be called on bad input")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.set_integrity_enabled",
            staticmethod(should_not_run),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"integrity_enabled": "yes-please"},
        )
        assert response.status_code in (400, 422)

    def test_set_typed_error_propagates(self, monkeypatch, test_client):
        def fail(value):
            raise Error("bad_request", "integrity_enabled must be a boolean")

        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.set_integrity_enabled",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"integrity_enabled": True},
        )
        assert response.status_code == 400

    def test_user_forbidden_set(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.backups.AdminBackupsService.set_integrity_enabled",
            staticmethod(lambda v: {"integrity_enabled": v}),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"integrity_enabled": True},
        )
        assert response.status_code == 403
