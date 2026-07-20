# SPDX-License-Identifier: AGPL-3.0-or-later

"""Admin stuck-delete inspect + recover routes.

``GET  /items/recycle-bin/stuck``         → list entries stranded mid-delete.
``POST /items/recycle-bin/recover-stuck`` → re-enqueue them (manual recovery).
"""

from unittest.mock import AsyncMock

from api.routes.tests.helpers import MockJWT


def test_list_stuck_entries(monkeypatch, test_client):
    jwt = MockJWT()  # admin
    captured = {}

    def fake_list(older_than_minutes=0):
        captured["older_than_minutes"] = older_than_minutes
        return [{"id": "rb-1", "status": "deleting", "storages_count": 2}]

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.list_stuck_entries",
        staticmethod(fake_list),
    )

    response = test_client(
        url="/items/recycle-bin/stuck?older_than_minutes=30", jwt=jwt
    )
    assert response.status_code == 200
    assert response.json()[0]["id"] == "rb-1"
    assert captured["older_than_minutes"] == 30


def test_recover_stuck_entries(monkeypatch, test_client):
    jwt = MockJWT()  # admin
    recover = AsyncMock(return_value=["rb-1", "rb-2"])
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.recover_stuck_entries",
        staticmethod(recover),
    )

    response = test_client(
        url="/items/recycle-bin/recover-stuck",
        method="POST",
        body={"older_than_minutes": 45},
        jwt=jwt,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert body["recovered"] == ["rb-1", "rb-2"]
    assert recover.await_args.kwargs["older_than_minutes"] == 45
