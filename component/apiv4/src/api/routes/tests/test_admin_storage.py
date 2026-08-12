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
    URL = "/admin/item/storage/status"

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
    URL = "/admin/items/storage"

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
    URL = "/admin/items/storage"

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
            url="/admin/items/storage/by-status/ready", jwt=MockJWT(role_id="admin")
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
            url="/admin/items/storage/by-status/ready",
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
            url="/admin/items/storage/domains/abc/disk.qcow2",
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
            url="/admin/items/media/domains/m-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["sid"] == "m-1"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_domains",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url="/admin/items/storage/domains/s-1", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/storage/{storage_id}
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteStorage:
    URL = "/admin/item/storage/s-99"

    def test_admin_deletes(self, monkeypatch, test_client):
        """Happy path: 202 + DeleteResponse with the cascade task_id.

        Mirrors the user-facing ``DELETE /item/storage/{id}`` contract
        (the admin endpoint was changed from a fire-and-forget 204
        mark-only path to the real cascade chain — see
        AdminStorageService.delete_storage docstring).
        """
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(
                lambda payload, sid: captured.update(payload=payload, sid=sid)
                or "task-abc"
            ),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 202
        assert captured["sid"] == "s-99"
        body = response.json()
        assert body["tasks_ids"] == ["task-abc"]

    def test_manager_allowed(self, monkeypatch, test_client):
        """Storage delete is on manager_router (managers handle their
        category's storages). If a future refactor moves it to admin_router,
        this test will start failing — make sure that's an intentional
        contract change.
        """
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(lambda payload, sid: called.update(yes=True) or "task-mgr"),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 202
        assert called["yes"] is True

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(lambda payload, sid: None),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_unknown_storage_returns_404(self, monkeypatch, test_client):
        def fail(payload, sid):
            raise Error("not_found", "Storage not found")

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_storage_with_children_returns_428(self, monkeypatch, test_client):
        """Precondition: deleting a parent storage that still has child
        storages must be rejected at the route layer with 428, never
        silently fired (the old behaviour orphaned the children)."""

        def fail(payload, sid):
            raise Error(
                "precondition_required",
                f"Storage {sid} has 2 child storage(s); delete them first.",
                description_code="storage_has_children",
            )

        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.delete_storage",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 428


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
            url="/admin/item/storage/info/s-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["format"] == "qcow2"

    def test_get_search_info(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.storage.AdminStorageService.get_storage_search_info",
            staticmethod(lambda payload, sid: {"id": sid, "owner": {"id": "u-1"}}),
        )
        response = test_client(
            url="/admin/item/storage/search-info/s-1", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["owner"]["id"] == "u-1"


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/storage/by-role/{role}  — admin-only
# ══════════════════════════════════════════════════════════════════════════


class TestStorageByRole:
    URL = "/admin/items/storage/by-role/manager"

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
            url="/admin/items/storage/by-role/invalid", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/storage/refresh-running-sizes
# ══════════════════════════════════════════════════════════════════════════


class TestRefreshRunningSizes:
    """The admin sweep that re-measures qemu-img-info for the disks of
    currently-running desktops, so a long-running desktop's stored
    ``actual-size`` doesn't stay frozen at its last stop.

    The real selection logic runs against the mock DB; only
    ``Storage.check_backing_chain`` (the RQ/redis enqueue boundary) is
    stubbed, capturing which storages would be refreshed.
    """

    URL = "/admin/storage/refresh-running-sizes"

    DB = {
        "domains": [
            {
                "id": "d-run",
                "status": "Started",
                "user": "u1",
                # A domain carries its disks under create_dict, not at the root:
                # that is where Domain.storages and the engine's post-stop
                # refresh read them. A root-level "hardware" is the shape the
                # sweep used to query, and it matches no real document.
                "create_dict": {
                    "hardware": {
                        "disks": [{"storage_id": "s-ready"}, {"storage_id": "s-ro"}]
                    }
                },
            },
            {
                "id": "d-stop",
                "status": "Stopped",
                "user": "u1",
                "create_dict": {"hardware": {"disks": [{"storage_id": "s-stopped"}]}},
            },
        ],
        "storage": [
            {
                "id": "s-ready",
                "status": "ready",
                "user_id": "u1",
                "directory_path": "/p",
                "type": "qcow2",
                "task": None,
            },
            {
                "id": "s-ro",
                "status": "ready",
                "readonly": True,
                "user_id": "u1",
                "directory_path": "/p",
                "type": "qcow2",
                "task": None,
            },
            {
                "id": "s-stopped",
                "status": "ready",
                "user_id": "u1",
                "directory_path": "/p",
                "type": "qcow2",
                "task": None,
            },
        ],
    }

    def _capture_cbc(self, monkeypatch):
        calls = []

        def fake_check_backing_chain(
            zelf, user_id, blocking=True, retry=3, priority="background"
        ):
            calls.append(
                {
                    "storage_id": zelf.id,
                    "user_id": user_id,
                    "blocking": blocking,
                    "retry": retry,
                    "priority": priority,
                }
            )
            return "task-id"

        monkeypatch.setattr(
            "isardvdi_common.models.storage.Storage.check_backing_chain",
            fake_check_backing_chain,
        )
        return calls

    def test_enqueues_only_running_ready_nonreadonly_disks(
        self, monkeypatch, test_client
    ):
        calls = self._capture_cbc(monkeypatch)
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            db_tables_data=self.DB,
        )
        assert response.status_code == 200
        assert response.json()["enqueued"] == 1
        # Only the running desktop's ready, non-readonly disk is refreshed:
        # the stopped desktop's disk and the read-only disk are skipped.
        assert [c["storage_id"] for c in calls] == ["s-ready"]
        # Best-effort, lowest priority so it never contends with
        # interactive disk operations.
        assert calls[0]["blocking"] is False
        assert calls[0]["priority"] == "background"
        assert calls[0]["user_id"] == "u1"

    def test_skips_storage_with_pending_refresh_task(self, monkeypatch, test_client):
        calls = self._capture_cbc(monkeypatch)

        # A refresh is already in flight for s-ready → it must be skipped
        # so repeated sweeps don't dogpile the task queue. The guard resolves
        # the row's live task through the index, so that is what the fake
        # answers; the row's ``task`` scalar is retired and no longer read.
        class _FakeTask:
            _redis = None


        # so repeated sweeps don't dogpile the task queue. Replace the
        # ``Task`` used by the sweep with a fake whose task is pending,
        # so the guard fires without touching redis.
        class _FakeTask:
            def __init__(self, task_id):
                self.pending = True

            @staticmethod
            def exists(task_id):
                return True

        monkeypatch.setattr("isardvdi_common.lib.storage.storage.Task", _FakeTask)
        monkeypatch.setattr(
            "isardvdi_common.lib.storage.storage.current_task_id",
            lambda _connection, storage_id, **kwargs: "task-in-flight",
        )

        db = {
            "domains": [
                {
                    "id": "d-run",
                    "status": "Started",
                    "user": "u1",
                    "create_dict": {"hardware": {"disks": [{"storage_id": "s-ready"}]}},
                }
            ],
            "storage": [
                {
                    "id": "s-ready",
                    "status": "ready",
                    "user_id": "u1",
                    "directory_path": "/p",
                    "type": "qcow2",
                    "task": "task-in-flight",
                }
            ],
        }
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            db_tables_data=db,
        )
        assert response.status_code == 200
        assert response.json()["enqueued"] == 0
        assert calls == []

    def test_manager_forbidden(self, monkeypatch, test_client):
        calls = self._capture_cbc(monkeypatch)
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            db_tables_data=self.DB,
        )
        assert response.status_code == 403
        assert calls == []
