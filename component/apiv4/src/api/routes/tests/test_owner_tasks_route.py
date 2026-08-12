#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The per-owner task listing, on the routes a user's own modal can call.

Deliberately ``token_router`` and not a filter on the admin listing: that one
is ``manager_router``, so it answers 403 to role ``user`` and the modal that
needs this could never call it.
"""

import pytest
from api.routes.tests.helpers import MockJWT
from api.services.error import Error

ROW = {
    "id": "job-1",
    "task": "convert",
    "queue": "storage.pool.default.default",
    "job_status": "finished",
    "user_id": "u-1",
    "category_id": "cat-1",
    "storage_id": "disk-1",
    "media_id": None,
    "enqueued_at": 1000.0,
    "started_at": 1001.0,
    "ended_at": 1009.0,
}


class TestStorageTasks:
    def test_the_owner_gets_the_rows(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.services.storage.StorageService.get_tasks",
            staticmethod(lambda payload, storage_id: [ROW]),
        )
        response = test_client(url="/item/storage/disk-1/tasks", jwt=MockJWT())
        assert response.status_code == 200
        body = response.json()
        assert [row["id"] for row in body] == ["job-1"]
        assert body[0]["storage_id"] == "disk-1"
        assert body[0]["job_status"] == "finished"

    def test_a_role_user_may_call_it(self, monkeypatch, test_client):
        """The whole point of putting it on ``token_router``."""
        monkeypatch.setattr(
            "api.services.storage.StorageService.get_tasks",
            staticmethod(lambda payload, storage_id: []),
        )
        response = test_client(
            url="/item/storage/disk-1/tasks", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_someone_elses_disk_is_refused(self, monkeypatch, test_client):
        """The ownership control is the one ``get_storage`` already applies to
        every per-item storage route; the route must surface its refusal."""

        def refuse(payload, storage_id):
            raise Error("forbidden", "Not enough access rights for this user_id")

        monkeypatch.setattr(
            "api.services.storage.StorageService.get_tasks", staticmethod(refuse)
        )
        response = test_client(
            url="/item/storage/someone-elses/tasks", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_a_missing_disk_is_404(self, monkeypatch, test_client):
        def missing(payload, storage_id):
            raise Error("not_found", "Storage ghost not found")

        monkeypatch.setattr(
            "api.services.storage.StorageService.get_tasks", staticmethod(missing)
        )
        response = test_client(url="/item/storage/ghost/tasks", jwt=MockJWT())
        assert response.status_code == 404

    def test_the_caller_never_picks_the_owner(self, monkeypatch, test_client):
        """The id comes off the path, which the ownership check reads too."""
        seen = {}

        def capture(payload, storage_id):
            seen["storage_id"] = storage_id
            return []

        monkeypatch.setattr(
            "api.services.storage.StorageService.get_tasks", staticmethod(capture)
        )
        test_client(url="/item/storage/disk-9/tasks", jwt=MockJWT())
        assert seen == {"storage_id": "disk-9"}


class TestMediaTasks:
    def test_the_owner_gets_the_rows(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.dependencies.alloweds.Helpers.owns_media_id",
            staticmethod(lambda payload, media_id: media_id),
        )
        monkeypatch.setattr(
            "api.services.tasks.TaskService.owner_tasks",
            staticmethod(lambda owner_id, kind="storage": [{**ROW, "media_id": "m-1"}]),
        )
        response = test_client(url="/item/media/m-1/tasks", jwt=MockJWT())
        assert response.status_code == 200
        assert response.json()[0]["media_id"] == "m-1"

    def test_it_reads_the_media_index_not_the_storage_one(
        self, monkeypatch, test_client
    ):
        seen = {}

        monkeypatch.setattr(
            "api.dependencies.alloweds.Helpers.owns_media_id",
            staticmethod(lambda payload, media_id: media_id),
        )

        def capture(owner_id, kind="storage"):
            seen.update(owner_id=owner_id, kind=kind)
            return []

        monkeypatch.setattr(
            "api.services.tasks.TaskService.owner_tasks", staticmethod(capture)
        )
        test_client(url="/item/media/m-1/tasks", jwt=MockJWT())
        assert seen == {"owner_id": "m-1", "kind": "media"}

    def test_it_inherits_medias_own_access_gate(self, test_client):
        """``owns_media_id`` depends on ``is_not_user``, so role ``user`` is
        refused on every media route including this one. That is media's
        existing policy, unchanged here — the storage twin is the one a plain
        user's modal calls."""
        response = test_client(url="/item/media/m-1/tasks", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403
