# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/tables.py — generic table CRUD endpoints used by the
admin UI's datatables.

Sanitization of HTML/XML field content lives in the service layer and
is exercised by ``test_admin_tables_sanitize.py``. This file pins the
ROUTE-level contract: auth gates, payload forwarding, error mapping.

Notable shape:
    GET  /admin/table/{table}             on manager_router
    POST /admin/table/{table}             on manager_router (filter+list)
    POST /admin/table/add/{table}         on admin_router
    PUT  /admin/table/update/{table}      on admin_router
    DELETE /admin/table/{table}/{id}      on admin_router

The admin/manager split is the security surface: managers can READ
table data (scoped to their category by the service); only admins
can mutate.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/table/{table}  (manager_router)
# ══════════════════════════════════════════════════════════════════════════


class TestGetTable:
    URL = "/admin/table/users"

    def test_admin_reads_table(self, monkeypatch, test_client):
        captured = {}

        def fake_get(table, payload, options):
            captured["table"] = table
            captured["role_id"] = payload["role_id"]
            captured["options"] = options
            return [{"id": "u-1"}, {"id": "u-2"}]

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["table"] == "users"
        assert captured["role_id"] == "admin"
        assert response.json()[0]["id"] == "u-1"

    def test_query_params_forwarded_as_options(self, monkeypatch, test_client):
        """The route packs request.query_params into a plain dict and
        forwards it as `options` to the service. Pin that contract so a
        future move to typed query params doesn't silently drop the
        manager-UI's filter args.
        """
        captured = {}

        def fake_get(table, payload, options):
            captured["options"] = options
            return []

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(
            url=f"{self.URL}?id=u-1&pluck=name", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["options"] == {"id": "u-1", "pluck": "name"}

    def test_manager_allowed_on_read(self, monkeypatch, test_client):
        """Read endpoints are on manager_router — managers must succeed
        (the service is responsible for category scoping).
        """
        captured = {}

        def fake_get(table, payload, options):
            captured["role_id"] = payload["role_id"]
            return []

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 200
        assert captured["role_id"] == "manager"

    def test_user_forbidden_on_read(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def fail(*a, **k):
            raise Error("not_found", "Unknown table")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fail),
        )
        response = test_client(
            url="/admin/table/no_such_table", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(*a, **k):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/table/{table}  (manager_router) — filter + list
# ══════════════════════════════════════════════════════════════════════════


class TestListTableWithFilters:
    URL = "/admin/table/users"

    def test_admin_filters(self, monkeypatch, test_client):
        captured = {}

        def fake_get(table, payload, options):
            captured["options"] = options
            return [{"id": "u-1"}]

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "id": "u-1",
                "index": "user_id",
                "order_by": "name",
                "pluck": ["id", "name"],
                "without": "password",
            },
        )
        assert response.status_code == 200
        assert captured["options"] == {
            "id": "u-1",
            "index": "user_id",
            "order_by": "name",
            "pluck": ["id", "name"],
            "without": "password",
        }

    def test_exclude_none_drops_unset_fields(self, monkeypatch, test_client):
        """The handler dumps the schema with exclude_none=True so the
        service receives only the keys the caller actually set, not
        a soup of nulls. Pin that — services that branch on `if "id" in
        options:` rely on it.
        """
        captured = {}

        def fake_get(table, payload, options):
            captured["options"] = options
            return []

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"order_by": "name"},
        )
        assert response.status_code == 200
        assert captured["options"] == {"order_by": "name"}

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url=self.URL, method="POST", jwt=MockJWT(role_id="user"), body={}
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/table/add/{table}  (admin_router) — DESTRUCTIVE
# ══════════════════════════════════════════════════════════════════════════


class TestInsertTableItem:
    URL = "/admin/table/add/users"

    def test_admin_inserts(self, monkeypatch, test_client):
        captured = {}

        def fake_insert(table, data):
            captured["table"] = table
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.insert_table_item",
            staticmethod(fake_insert),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "u-new", "name": "newuser"},
        )
        assert response.status_code == 200
        assert captured == {
            "table": "users",
            "data": {"id": "u-new", "name": "newuser"},
        }

    def test_duplicate_returns_409(self, monkeypatch, test_client):
        def reject(table, data):
            raise Error("conflict", "Item with that name already exists")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.insert_table_item",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"name": "dup"},
        )
        assert response.status_code == 409

    def test_manager_forbidden(self, monkeypatch, test_client):
        """Mutating endpoints sit on admin_router — managers must NOT
        be able to insert into shared tables.
        """
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.insert_table_item",
            staticmethod(lambda t, d: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"id": "u-new"},
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.insert_table_item",
            staticmethod(lambda t, d: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"id": "u-new"},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/table/update/{table}  (admin_router) — DESTRUCTIVE
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateTableItem:
    URL = "/admin/table/update/users"

    def test_admin_updates(self, monkeypatch, test_client):
        captured = {}

        def fake_update(table, data):
            captured["table"] = table
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.update_table_item",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"id": "u-1", "name": "renamed"},
        )
        assert response.status_code == 200
        assert captured["data"]["name"] == "renamed"

    def test_unknown_item_returns_404(self, monkeypatch, test_client):
        def fail(table, data):
            raise Error("not_found", "Item not found")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.update_table_item",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"id": "ghost"},
        )
        assert response.status_code == 404

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.update_table_item",
            staticmethod(lambda t, d: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"id": "u-1"},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/table/{table}/{item_id}  (admin_router) — DESTRUCTIVE
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteTableItem:
    URL = "/admin/table/users/u-99"

    def test_admin_deletes(self, monkeypatch, test_client):
        captured = {}

        def fake_delete(table, item_id):
            captured["table"] = table
            captured["item_id"] = item_id

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.delete_table_item",
            staticmethod(fake_delete),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured == {"table": "users", "item_id": "u-99"}

    def test_unknown_item_returns_404(self, monkeypatch, test_client):
        def fail(table, item_id):
            raise Error("not_found", "Item not found")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.delete_table_item",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.delete_table_item",
            staticmethod(lambda t, i: None),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.delete_table_item",
            staticmethod(lambda t, i: None),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(table, item_id):
            raise RuntimeError("Cascade delete failed")

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.delete_table_item",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 500
