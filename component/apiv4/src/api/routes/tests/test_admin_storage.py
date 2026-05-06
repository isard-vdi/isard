# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/storage.py — admin/manager storage listings, status
counts, per-domain lookups, info, search-info, delete, and the admin-only
by-role listing.

Most endpoints sit on manager_router (admin + manager allowed); the
``/admin/storage/by-role/{role}`` endpoint is admin-only because it
crosses category boundaries.

Note: the storage delete endpoint sits on manager_router by design
(per the v3 contract: managers can delete storages within their
category). The service is responsible for the category check; if it's
removed in a refactor, managers would gain cross-category delete
power. The TestDeleteStorage tests pin manager-allowed + service-call
forwarding so a future refactor that moves the gate elsewhere has to
update this test in the same commit.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /storage/status
# ══════════════════════════════════════════════════════════════════════════


class TestGetStorageStatus:
    URL = "/storage/status"

    def test_admin_gets_counts(self, monkeypatch, test_client):
        captured = {}

        def fake(payload):
            captured["role_id"] = payload["role_id"]
            # Real ``MediaProcessed.admin_get_storage_status`` returns
            # a list of ``{status, count}`` rows; the response_model
            # now enforces that. Old stub returned ``{ready: 5}``.
            return [{"status": "ready", "count": 5}]

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_status",
            staticmethod(fake),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        ready = next(row for row in body if row["status"] == "ready")
        assert ready["count"] == 5

    def test_manager_allowed(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_status",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 200

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_status",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage  (list)
# ══════════════════════════════════════════════════════════════════════════


class TestListStorage:
    URL = "/admin/storage"

    def test_admin_lists(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(lambda payload: [{"id": "s1"}]),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "s1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(lambda payload: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/storage  (filter by categories)
# ══════════════════════════════════════════════════════════════════════════


class TestListStorageFiltered:
    URL = "/admin/storage"

    def test_categories_forwarded(self, monkeypatch, test_client):
        captured = {}

        def fake(payload, categories=None):
            captured["categories"] = categories
            return []

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": ["cat-a", "cat-b"]},
        )
        assert response.status_code == 200
        assert captured["categories"] == ["cat-a", "cat-b"]

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"categories": []},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage/by-status/{status}
# ══════════════════════════════════════════════════════════════════════════


class TestStorageByStatus:
    def test_status_passed_as_kwarg(self, monkeypatch, test_client):
        captured = {}

        def fake(payload, status=None):
            captured["status"] = status
            return []

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/storage/by-status/ready", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["status"] == "ready"

    def test_post_variant_filters_by_categories(self, monkeypatch, test_client):
        captured = {}

        def fake(payload, status=None, categories=None):
            captured["status"] = status
            captured["categories"] = categories
            return []

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/storage/by-status/ready",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": ["cat-a"]},
        )
        assert response.status_code == 200
        assert captured == {"status": "ready", "categories": ["cat-a"]}


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage/domains/{storage_id:path}
#  GET /admin/media/domains/{storage_id:path}
# ══════════════════════════════════════════════════════════════════════════


class TestDomainsByStorage:
    """The :path converter on storage_id allows slashes — relevant because
    storage IDs can be filesystem paths (e.g. /isard/storage/abc/disk.qcow2).
    Pin that the slashed id reaches the service intact.
    """

    def test_storage_domains_with_slashed_id(self, monkeypatch, test_client):
        captured = {}

        def fake(payload, sid):
            captured["sid"] = sid
            return [{"id": "d1"}]

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_domains",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/storage/domains/abc/disk.qcow2",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["sid"] == "abc/disk.qcow2"

    def test_media_domains(self, monkeypatch, test_client):
        captured = {}

        def fake(payload, sid):
            captured["sid"] = sid
            return [{"id": "d1"}]

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_media_domains",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/media/domains/m-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["sid"] == "m-1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_domains",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url="/admin/storage/domains/s-1", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/storage/{storage_id}
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteStorage:
    URL = "/admin/storage/s-99"

    def test_admin_deletes(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(lambda sid: captured.update(sid=sid)),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 204
        assert captured["sid"] == "s-99"

    def test_manager_allowed(self, monkeypatch, test_client):
        """Storage delete is on manager_router (managers handle their
        category's storages). If a future refactor moves it to admin_router,
        this test will start failing — make sure that's an intentional
        contract change.
        """
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(lambda sid: called.update(yes=True)),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 204
        assert called["yes"] is True

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(lambda sid: None),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_unknown_storage_returns_404(self, monkeypatch, test_client):
        def fail(sid):
            raise Error("not_found", "Storage not found")

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage/info/{id}, /admin/storage/search-info/{id}
# ══════════════════════════════════════════════════════════════════════════


class TestStorageInfoEndpoints:
    def test_get_info(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_info",
            staticmethod(lambda payload, sid: {"id": sid, "format": "qcow2"}),
        )
        response = test_client(
            url="/admin/storage/info/s-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["format"] == "qcow2"

    def test_get_search_info(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_search_info",
            staticmethod(lambda payload, sid: {"id": sid, "owner": {"id": "u-1"}}),
        )
        response = test_client(
            url="/admin/storage/search-info/s-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["owner"]["id"] == "u-1"


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage/by-role/{role}  — admin-only
# ══════════════════════════════════════════════════════════════════════════


class TestStorageByRole:
    URL = "/admin/storage/by-role/manager"

    def test_admin_filters_by_role(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages_by_role",
            staticmethod(lambda role: captured.update(role=role) or []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["role"] == "manager"

    def test_manager_forbidden(self, monkeypatch, test_client):
        """admin_router endpoint — managers must NOT be able to query
        across categories. A future refactor that moves this to
        manager_router would let a manager enumerate every other
        category's storages.
        """
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages_by_role",
            staticmethod(lambda role: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages_by_role",
            staticmethod(lambda role: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_invalid_role_returns_400(self, monkeypatch, test_client):
        def reject(role):
            raise Error("bad_request", f"Invalid role: {role}")

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storages_by_role",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/storage/by-role/invalid", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 400
