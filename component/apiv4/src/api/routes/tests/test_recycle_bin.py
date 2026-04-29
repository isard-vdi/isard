# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_get_recycle_bin_default_delete_config(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_default_delete_config",
        staticmethod(lambda: True),
    )
    response = test_client(url="/item/recycle-bin/get-default-delete-config", jwt=jwt)
    assert response.status_code == 200
    assert response.json() is True


def test_get_recycle_bin_count(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_user_count",
        staticmethod(lambda user_id: 5),
    )
    response = test_client(url="/item/recycle-bin/count", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == 5


def test_get_recycle_bin_entries(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_user_recycle_bin_entries",
        staticmethod(lambda user_id: []),
    )
    response = test_client(url="/items/recycle-bin", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_empty_recycle_bin(monkeypatch, test_client):
    jwt = MockJWT()

    async def mock_empty(user_id):
        return None

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.empty_user_recycle_bin",
        staticmethod(mock_empty),
    )
    response = test_client(url="/item/recycle-bin/empty", method="DELETE", jwt=jwt)
    assert response.status_code == 202


def test_get_recycle_bin_cutoff_time(monkeypatch, test_client):
    """Vue 2 reads ``recycle_bin_cuttoff_time`` (double-t typo from
    the apiv3 contract) and renders ``NaN`` when the key is missing.
    The endpoint must keep emitting both spellings so Vue 2 (typo)
    and Vue 3 (corrected) both work.
    """
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_user_cutoff_time",
        staticmethod(lambda category_id: 30),
    )
    response = test_client(url="/item/recycle-bin/get-user-cutoff-time", jwt=jwt)
    assert response.status_code == 200
    body = response.json()
    assert body["recycle_bin_cutoff_time"] == 30
    assert body["recycle_bin_cuttoff_time"] == 30


# ─── Admin recycle bin entry listing (manager_router) ────────────────────
# Replaces the three v3 shims /recycle_bin/item_count[/status/{status}]
# and /recycle_bin/status. The new /items/recycle-bin/admin-entries route
# exposes RecycleBinService.get_item_count with an optional ?status query
# param and enforces manager-category scoping.


def test_get_admin_recycle_bin_entries_manager_scoped(monkeypatch, test_client):
    # Manager JWT triggers the has_token maintenance check, which queries
    # r.table("categories").get(category_id). Seed a matching row so the
    # mock DB returns the caller's category and not None.
    jwt = MockJWT(role_id="manager", category_id="cat-manager")
    stub = [
        {
            "id": "rb-1",
            "status": "recycled",
            "desktops": 2,
            "templates": 0,
            "storages": 1,
            "deployments": 0,
        }
    ]
    captured = {}

    def fake_get_item_count(category_id=None, status=None):
        captured["category_id"] = category_id
        captured["status"] = status
        return stub

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_item_count",
        staticmethod(fake_get_item_count),
    )

    response = test_client(
        url="/items/recycle-bin/admin-entries",
        jwt=jwt,
        db_tables_data={
            "categories": [
                {"id": "cat-manager", "maintenance": False},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == stub
    # Manager role → scoped to the manager's own category, no status filter
    assert captured == {"category_id": "cat-manager", "status": None}


def test_get_admin_recycle_bin_entries_admin_sees_all(monkeypatch, test_client):
    jwt = MockJWT()  # default role_id="admin"
    captured = {}

    def fake_get_item_count(category_id=None, status=None):
        captured["category_id"] = category_id
        captured["status"] = status
        return []

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_item_count",
        staticmethod(fake_get_item_count),
    )

    response = test_client(url="/items/recycle-bin/admin-entries", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == []
    # Admin role → category_id is None (global view)
    assert captured == {"category_id": None, "status": None}


# ─── Config + rules + bulk ops (T1/recycle_bin shim replacements) ──────


def test_restore_recycle_bin(monkeypatch, test_client):
    """The restore route is bound with ``owns_recycle_bin_id`` which
    short-circuits for admin role — the default ``MockJWT()`` already
    passes it so no dependency override is needed."""
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.restore_recycle_bin_entry",
        staticmethod(lambda recycle_bin_id: calls.append(recycle_bin_id)),
    )

    response = test_client(
        url="/item/recycle-bin/rb-1/restore",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "rb-1"}
    assert calls == ["rb-1"]


def test_bulk_restore_recycle_bin(monkeypatch, test_client):
    """RecycleBinBulkResponse has only ``success`` and ``failed`` fields —
    the route passes ``recycle_bin_ids=ids`` but pydantic drops the
    unknown key, so the wire response is ``{success: [], failed: []}``.
    The test pins that shape so a future fix (renaming the schema field
    to match the intended name) is flagged."""
    jwt = MockJWT()
    captured = {}

    async def fake_bulk_restore(recycle_bin_ids, user_id):
        captured["ids"] = recycle_bin_ids
        captured["user_id"] = user_id
        return recycle_bin_ids

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.bulk_restore",
        staticmethod(fake_bulk_restore),
    )

    response = test_client(
        url="/items/recycle-bin/restore",
        method="PUT",
        body={"recycle_bin_ids": ["rb-1", "rb-2"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"success": [], "failed": []}
    assert captured == {
        "ids": ["rb-1", "rb-2"],
        "user_id": jwt.payload["user_id"],
    }


def test_bulk_delete_recycle_bin(monkeypatch, test_client):
    """Same RecycleBinBulkResponse shape mismatch as bulk_restore."""
    jwt = MockJWT()

    async def fake_bulk_delete(recycle_bin_ids, user_id):
        return recycle_bin_ids

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.bulk_delete",
        staticmethod(fake_bulk_delete),
    )

    response = test_client(
        url="/items/recycle-bin/delete",
        method="PUT",
        body={"recycle_bin_ids": ["rb-1"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"success": [], "failed": []}


def test_set_old_entries_max_time(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.set_old_entries_max_time",
        staticmethod(lambda max_time: calls.append(max_time) or {}),
    )

    response = test_client(
        url="/item/recycle-bin/old-entries/max-time/2592000",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["2592000"]


def test_set_old_entries_action(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.set_old_entries_action",
        staticmethod(lambda action: calls.append(action) or {}),
    )

    response = test_client(
        url="/item/recycle-bin/old-entries/action/delete",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["delete"]


def test_get_old_entries_config(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"max_time": 604800, "action": "delete"}
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_old_entries_config",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/item/recycle-bin/old-entries/config", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_get_delete_action(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_delete_action",
        staticmethod(lambda: "recycle"),
    )

    response = test_client(url="/item/recycle-bin/config/delete-action", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == "recycle"


def test_set_delete_action(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.set_delete_action",
        staticmethod(lambda action: calls.append(action)),
    )

    response = test_client(
        url="/item/recycle-bin/config/delete-action/permanent",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["permanent"]


def test_set_default_delete(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.set_default_delete",
        staticmethod(lambda rb_default: calls.append(rb_default)),
    )

    response = test_client(
        url="/item/recycle-bin/config/default-delete",
        method="PUT",
        body={"rb_default": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == [True]


def test_get_all_unused_item_timeout_rules(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {
            "id": "rule-1",
            "name": "Old desktops",
            "description": "",
            "timeout": 30,
            "enabled": True,
        }
    ]
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_all_unused_item_timeout_rules",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/items/recycle-bin/unused-item-timeout-rules", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"rules": stub}


def test_create_unused_item_timeout_rule(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(data):
        captured["name"] = data["name"]
        captured["timeout"] = data["timeout"]
        return "rule-new"

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.create_unused_item_timeout_rule",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/items/recycle-bin/unused-item-timeout-rules",
        method="POST",
        body={
            "name": "Old desktops",
            "description": "",
            "timeout": 30,
            "enabled": True,
        },
        jwt=jwt,
    )

    assert response.status_code == 201
    assert response.json() == {"id": "rule-new"}
    assert captured == {"name": "Old desktops", "timeout": 30}


def test_get_system_cutoff_time(monkeypatch, test_client):
    jwt = MockJWT()  # admin → route passes category_id=None
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_system_cutoff_time",
        staticmethod(lambda category_id=None: 60),
    )

    response = test_client(url="/item/recycle-bin/system/cutoff-time", jwt=jwt)

    assert response.status_code == 200
    assert response.json()["recycle_bin_cuttoff_time"] == 60


def test_set_system_cutoff_time(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set(cutoff_time, category_id=None):
        captured["cutoff_time"] = cutoff_time
        captured["category_id"] = category_id

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.set_system_cutoff_time",
        staticmethod(fake_set),
    )

    response = test_client(
        url="/item/recycle-bin/system/cutoff-time",
        method="PUT",
        body={"recycle_bin_cuttoff_time": 90},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"cutoff_time": 90, "category_id": None}


def test_get_admin_recycle_bin_entries_filtered_by_status(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_get_item_count(category_id=None, status=None):
        captured["category_id"] = category_id
        captured["status"] = status
        return []

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_item_count",
        staticmethod(fake_get_item_count),
    )

    response = test_client(
        url="/items/recycle-bin/admin-entries?status=deleted", jwt=jwt
    )

    assert response.status_code == 200
    assert captured == {"category_id": None, "status": "deleted"}
