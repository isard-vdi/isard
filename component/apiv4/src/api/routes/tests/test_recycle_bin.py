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
    """``RecycleBinBulkResponse`` now carries ``recycle_bin_ids``
    matching what the service scheduled. Pre-fix the schema declared
    ``success`` / ``failed`` and the route's
    ``RecycleBinBulkResponse(recycle_bin_ids=ids)`` had its kwarg
    silently dropped, so the wire response was always
    ``{success: [], failed: []}``. Pin the real round-trip so the
    OAS-generated vue3 client can correlate per-item outcomes."""
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
    assert response.json() == {"recycle_bin_ids": ["rb-1", "rb-2"]}
    assert captured == {
        "ids": ["rb-1", "rb-2"],
        "user_id": jwt.payload["user_id"],
    }


def test_bulk_restore_recycle_bin_forbidden_for_non_owner(monkeypatch, test_client):
    """Pre-fix: any authenticated user could PUT a list of arbitrary
    rb_ids and have them restored — apiv3 enforced
    ``ownsRecycleBinId`` per id (``main:api/src/api/views/RecycleBinView.py:111-112``);
    apiv4 dropped the loop. Pin that the route now raises 403 on the
    first non-owned id BEFORE spawning the background task."""
    from api.services.error import Error

    jwt = MockJWT(role_id="user", user_id="local-default-bob-bob")
    captured = {"called": False}

    async def fake_bulk_restore(recycle_bin_ids, user_id):
        captured["called"] = True
        return recycle_bin_ids

    def fake_owns(payload, rb_id):
        # Caller is "bob" but the rb is owned by another user → forbidden.
        raise Error(
            "forbidden",
            f"Not enough access rights for this user_id {payload['user_id']}",
        )

    monkeypatch.setattr(
        "api.routes.recycle_bin.RecycleBinHelpers.owns_recycle_bin_id",
        staticmethod(fake_owns),
    )
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.bulk_restore",
        staticmethod(fake_bulk_restore),
    )

    response = test_client(
        url="/items/recycle-bin/restore",
        method="PUT",
        body={"recycle_bin_ids": ["rb-owned-by-alice"]},
        jwt=jwt,
    )

    assert response.status_code == 403
    # The service MUST NOT run when the ownership check fails.
    assert captured["called"] is False


def test_bulk_delete_recycle_bin_forbidden_for_non_owner(monkeypatch, test_client):
    """Same per-id ownership contract as bulk_restore."""
    from api.services.error import Error

    jwt = MockJWT(role_id="user", user_id="local-default-bob-bob")
    captured = {"called": False}

    async def fake_bulk_delete(recycle_bin_ids, user_id):
        captured["called"] = True
        return recycle_bin_ids

    def fake_owns(payload, rb_id):
        raise Error("forbidden", "nope")

    monkeypatch.setattr(
        "api.routes.recycle_bin.RecycleBinHelpers.owns_recycle_bin_id",
        staticmethod(fake_owns),
    )
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.bulk_delete",
        staticmethod(fake_bulk_delete),
    )

    response = test_client(
        url="/items/recycle-bin/delete",
        method="PUT",
        body={"recycle_bin_ids": ["rb-owned-by-alice"]},
        jwt=jwt,
    )

    assert response.status_code == 403
    assert captured["called"] is False


def test_bulk_delete_recycle_bin(monkeypatch, test_client):
    """Same ``recycle_bin_ids`` round-trip contract as bulk_restore."""
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
    assert response.json() == {"recycle_bin_ids": ["rb-1"]}


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

    assert response.status_code == 204
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

    assert response.status_code == 204
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

    assert response.status_code == 204
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

    assert response.status_code == 204
    assert calls == [True]


def test_get_all_unused_item_timeout_rules(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {
            "id": "rule-1",
            "name": "Old desktops",
            "description": "",
            "op": "send_unused_desktops_to_recycle_bin",
            "cutoff_time": 720,
            "priority": 10,
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
        }
    ]
    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.get_all_unused_item_timeout_rules",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/items/recycle-bin/unused-item-timeout-rules", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"rules": stub}


def test_create_unused_item_timeout_rule_accepts_webapp_payload(
    monkeypatch, test_client
):
    """Apiv4 schema and the webapp admin form must agree on the field
    set. Pre-fix the schema required ``timeout`` / ``enabled`` and
    silently dropped ``op`` / ``cutoff_time`` / ``priority``, so every
    submit from ``recycle_bin_config.js`` 422-ed.

    Apiv3 reference: ``main:api/src/api/schemas/unused_item_timeout.yml``
    requires ``name`` / ``op`` / ``cutoff_time`` / ``priority``;
    ``cutoff_time`` is nullable. Pin the exact webapp payload shape so
    the contract can't drift again."""
    jwt = MockJWT()
    captured = {}

    def fake_create(data):
        captured.update(data)
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
            "description": "Older than 30 days",
            "op": "send_unused_desktops_to_recycle_bin",
            "cutoff_time": 720,
            "priority": 10,
        },
        jwt=jwt,
    )

    assert response.status_code == 201
    assert response.json() == {"id": "rule-new"}
    assert captured["name"] == "Old desktops"
    assert captured["op"] == "send_unused_desktops_to_recycle_bin"
    assert captured["cutoff_time"] == 720
    assert captured["priority"] == 10


def test_create_unused_item_timeout_rule_accepts_null_cutoff(monkeypatch, test_client):
    """``cutoff_time`` is nullable in apiv3 (``nullable: true``) and the
    webapp sends ``null`` to mean "no automatic cutoff"."""
    jwt = MockJWT()
    captured = {}

    def fake_create(data):
        captured.update(data)
        return "rule-null"

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.create_unused_item_timeout_rule",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/items/recycle-bin/unused-item-timeout-rules",
        method="POST",
        body={
            "name": "Never expire",
            "description": "",
            "op": "send_unused_desktops_to_recycle_bin",
            "cutoff_time": None,
            "priority": 0,
        },
        jwt=jwt,
    )

    assert response.status_code == 201
    assert captured["cutoff_time"] is None


def test_update_unused_item_timeout_rule_persists_priority(monkeypatch, test_client):
    """Webapp PUT sends the same payload shape as POST. Pin that
    ``priority`` and ``cutoff_time`` reach the helper."""
    jwt = MockJWT()
    captured = {}

    def fake_update(rule_id, data):
        captured["rule_id"] = rule_id
        captured.update(data)

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.update_unused_item_timeout_rule",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/item/recycle-bin/unused-item-timeout-rule/rule-1",
        method="PUT",
        body={
            "name": "Old desktops v2",
            "description": "Updated",
            "op": "send_unused_desktops_to_recycle_bin",
            "cutoff_time": 1440,
            "priority": 20,
        },
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured["rule_id"] == "rule-1"
    assert captured["priority"] == 20
    assert captured["cutoff_time"] == 1440


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


def test_recycle_bin_add_unused_items_invokes_service(monkeypatch, test_client):
    """Pre-fix the route called the non-existent
    ``RecycleBinService.delete_item`` and swallowed the
    ``AttributeError`` via ``except Exception: pass``. The endpoint
    returned 200 every night and the bin stayed empty.

    Pin that the route now invokes ``RecycleBinService.recycle_unused_items``
    via ``asyncio.to_thread`` and surfaces failures as 500 (no silent
    swallow). Mirror of apiv3
    ``main:api/src/api/views/RecycleBinView.py:599-672``.
    """
    jwt = MockJWT(role_id="admin")
    calls = {"count": 0}

    def fake_recycle_unused_items():
        calls["count"] += 1

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.recycle_unused_items",
        staticmethod(fake_recycle_unused_items),
    )

    response = test_client(url="/recycle-bin/unused-items", method="POST", jwt=jwt)

    assert response.status_code == 204
    assert calls == {"count": 1}


def test_recycle_bin_add_unused_items_surfaces_errors(monkeypatch, test_client):
    """The pre-fix route had ``except Exception: pass`` inside the
    per-desktop loop. Pin that errors propagating out of the service
    layer now surface as 500 — the scheduler MUST see them so admins
    notice when the cron is broken."""
    jwt = MockJWT(role_id="admin")

    def fake_recycle_unused_items():
        raise RuntimeError("rdb unreachable")

    monkeypatch.setattr(
        "api.services.recycle_bin.RecycleBinService.recycle_unused_items",
        staticmethod(fake_recycle_unused_items),
    )

    response = test_client(url="/recycle-bin/unused-items", method="POST", jwt=jwt)

    assert response.status_code == 500
