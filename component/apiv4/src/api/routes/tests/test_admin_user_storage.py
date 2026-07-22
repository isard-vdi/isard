# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/user_storage.py — provider auto-register, connection
test, login auth, list/get/delete, reset (per-provider + all),
add-provider (auth-protocol dispatched), and sync. All endpoints live
on admin_router (admin-only); user_storage carries credentials so
manager scope is intentionally excluded.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/user_storage/auto_register
# ══════════════════════════════════════════════════════════════════════════


class TestAutoRegister:
    URL = "/admin/user_storage/auto_register"

    def _payload(self, **overrides):
        body = {
            "domain": "https://nextcloud.example.com",
            "user": "admin",
            "password": "s3cret",
            "intra_docker": False,
            "verify_cert": True,
        }
        body.update(overrides)
        return body

    def test_admin_auto_registers(self, monkeypatch, test_client):
        captured = {}

        def fake(domain, user, password, intra_docker, verify_cert):
            captured["domain"] = domain
            captured["intra_docker"] = intra_docker
            captured["verify_cert"] = verify_cert
            return "provider-123"

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.auto_register",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert response.json()["id"] == "provider-123"
        assert captured["domain"] == "https://nextcloud.example.com"

    def test_missing_required_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"domain": "x"},  # password / user / etc missing
        )
        assert response.status_code in (400, 422)

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.auto_register",
            staticmethod(lambda *a, **k: ""),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=self._payload(),
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.auto_register",
            staticmethod(lambda *a, **k: ""),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/user_storage/conn_test
# ══════════════════════════════════════════════════════════════════════════


class TestConnTest:
    URL = "/admin/user_storage/conn_test"

    def _payload(self, **overrides):
        body = {
            "provider": "nextcloud",
            "url": "https://nc.example.com",
            "urlprefix": "/remote.php/dav/",
            "user": "admin",
            "password": "s3cret",
            "verify_cert": True,
        }
        body.update(overrides)
        return body

    def test_admin_tests_connection(self, monkeypatch, test_client):
        captured = {}

        def fake(provider, url, urlprefix, user, password, verify_cert):
            captured["provider"] = provider
            captured["password_passed"] = password == "s3cret"

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.conn_test",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 204
        # Sanity: the password actually reaches the service. Otherwise
        # a refactor that drops it from the call signature would silently
        # test against the empty string and report success.
        assert captured["password_passed"] is True

    def test_typed_error_on_bad_credentials(self, monkeypatch, test_client):
        def reject(*a, **k):
            raise Error("unauthorized", "Invalid credentials")

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.conn_test",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/user_storage/{provider_id}/login_auth
# ══════════════════════════════════════════════════════════════════════════


class TestLoginAuth:
    def test_admin_gets_login_url(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.get_login_auth",
            staticmethod(
                lambda pid: captured.update(pid=pid)
                or "https://oauth.example.com/authorize"
            ),
        )
        response = test_client(
            url="/admin/user_storage/p-1/login_auth",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert response.json()["login_url"] == "https://oauth.example.com/authorize"
        assert captured["pid"] == "p-1"


# ══════════════════════════════════════════════════════════════════════════
#  List / Get / Delete providers
# ══════════════════════════════════════════════════════════════════════════


class TestListGetDelete:
    def test_list_providers(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.list_providers",
            staticmethod(lambda: [{"id": "p1"}, {"id": "p2"}]),
        )
        response = test_client(url="/admin/user_storage", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_users(self, monkeypatch, test_client):
        """The /admin/user_storage/users endpoint MUST be declared before
        /admin/user_storage/{provider_id} — otherwise the catch-all
        matches "users" as a provider_id and get_provider("users")
        runs (silently 404 or returns garbage). Pin this declaration
        order trap.
        """
        called_get_provider = {}

        def get_provider_should_not_run(pid):
            called_get_provider["pid"] = pid
            raise AssertionError(
                "/admin/user_storage/users matched the {provider_id} catch-all"
            )

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.get_provider",
            staticmethod(get_provider_should_not_run),
        )
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.get_users",
            staticmethod(lambda: [{"id": "u-1"}]),
        )
        response = test_client(
            url="/admin/user_storage/users", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()[0]["id"] == "u-1"

    def test_get_provider(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.get_provider",
            staticmethod(lambda pid: {"id": pid, "name": "Nextcloud"}),
        )
        response = test_client(
            url="/admin/user_storage/p-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["id"] == "p-1"

    def test_get_unknown_provider_returns_404(self, monkeypatch, test_client):
        def fail(pid):
            raise Error("not_found", "Provider not found")

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.get_provider",
            staticmethod(fail),
        )
        response = test_client(
            url="/admin/user_storage/ghost", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_delete_provider(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.delete_provider",
            staticmethod(lambda pid: captured.update(pid=pid)),
        )
        response = test_client(
            url="/admin/user_storage/p-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured["pid"] == "p-1"

    def test_user_forbidden_on_delete(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.delete_provider",
            staticmethod(lambda pid: None),
        )
        response = test_client(
            url="/admin/user_storage/p-1",
            method="DELETE",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Reset
# ══════════════════════════════════════════════════════════════════════════


class TestReset:
    def test_reset_provider(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.reset_provider",
            staticmethod(lambda pid: captured.update(pid=pid)),
        )
        response = test_client(
            url="/admin/user_storage/p-1/reset",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured["pid"] == "p-1"

    def test_reset_all(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.reset_all",
            staticmethod(lambda: called.update(yes=True)),
        )
        response = test_client(
            url="/admin/user_storage/reset/all",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert called["yes"] is True

    def test_user_forbidden_on_reset_all(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.reset_all",
            staticmethod(lambda: None),
        )
        response = test_client(
            url="/admin/user_storage/reset/all",
            method="DELETE",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/user_storage/new/{auth_protocol}  — protocol dispatch
# ══════════════════════════════════════════════════════════════════════════


class TestAddProvider:
    def _payload(self, **overrides):
        body = {
            "provider": "nextcloud",
            "name": "Personal NC",
            "description": "User personal Nextcloud",
            "url": "https://nc.example.com",
            "urlprefix": "/remote.php/dav/",
            "access": "ro",
            "quota": 0,
            "verify_cert": True,
        }
        body.update(overrides)
        return body

    def test_basic_auth_routes_to_basic_helper(self, monkeypatch, test_client):
        captured = {}

        def fake(provider, name, description, url, urlprefix, access, quota, verify):
            captured["provider"] = provider
            captured["url"] = url
            return "p-new"

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.add_provider_basic_auth",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/user_storage/new/auth_basic",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert response.json()["id"] == "p-new"
        assert captured["url"] == "https://nc.example.com"

    def test_unsupported_auth_protocol_returns_400(self, test_client):
        """Only auth_basic is wired today; other protocols must
        return 400 (Error("bad_request")), NOT a generic 500.
        """
        response = test_client(
            url="/admin/user_storage/new/auth_oauth2",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.add_provider_basic_auth",
            staticmethod(lambda *a, **k: ""),
        )
        response = test_client(
            url="/admin/user_storage/new/auth_basic",
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/user_storage/{id}/sync/{item}
# ══════════════════════════════════════════════════════════════════════════


class TestSync:
    def test_admin_syncs_groups(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.sync",
            staticmethod(lambda pid, item: captured.update(pid=pid, item=item)),
        )
        response = test_client(
            url="/admin/user_storage/p-1/sync/groups",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured == {"pid": "p-1", "item": "groups"}

    def test_admin_syncs_users(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.sync",
            staticmethod(lambda pid, item: captured.update(pid=pid, item=item)),
        )
        response = test_client(
            url="/admin/user_storage/p-1/sync/users",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured["item"] == "users"

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(pid, item):
            raise Error("bad_request", f"Unknown sync item: {item}")

        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.sync",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/user_storage/p-1/sync/no_such_item",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.user_storage.AdminUserStorageService.sync",
            staticmethod(lambda pid, item: None),
        )
        response = test_client(
            url="/admin/user_storage/p-1/sync/all",
            method="PUT",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403
