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

    def test_non_utf8_bytes_do_not_500(self, monkeypatch, test_client):
        """RethinkDB rows can carry ``bytes`` values with non-UTF8 content
        (observed 0xb5 = µ in latin-1 on the domains table during 2026-05-14
        load tests). ``TableItem(**row).model_dump(mode="json")`` 500'd the
        whole admin DataTables page; ``_sanitize_bytes`` at the route
        boundary decodes with errors="replace" so the row still surfaces.
        """

        def fake_get(table, payload, options):
            return [{"id": "dom-1", "description": b"\xb5 binary blob"}]

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        assert body[0]["id"] == "dom-1"
        # 0xb5 is not valid UTF-8 — decoded with errors="replace" so it
        # surfaces as U+FFFD (replacement character) instead of vanishing.
        assert "�" in body[0]["description"]
        assert "binary blob" in body[0]["description"]

    def test_int_id_does_not_500(self, monkeypatch, test_client):
        """RethinkDB's ``config`` singleton row is stored with
        ``id=1`` (integer). The earlier ``TableItem.id: Optional[str]``
        annotation rejected the int and 500'd every
        ``GET /admin/table/config`` query — surfaced by pentest scans
        against the admin surface. The model now accepts ``Union[str,
        int]`` per the ``Pydantic model vs DB convention`` recurring
        pattern documented in the apiv4-migration skill."""

        def fake_get(table, payload, options):
            return [{"id": 1, "version": 193}]

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(
            url="/admin/table/config", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        body = response.json()
        assert body[0]["id"] == 1
        assert body[0]["version"] == 193

    def test_nested_bytes_in_dict_are_sanitized(self, monkeypatch, test_client):
        """Nested dicts/lists carrying bytes must also be decoded. The
        sanitizer recurses so a binary blob inside ``hardware.disks[0]``
        doesn't 500 the row."""

        def fake_get(table, payload, options):
            return [
                {
                    "id": "dom-1",
                    "hardware": {
                        "disks": [{"path": b"/isard/templates/\xb5.qcow2"}],
                    },
                }
            ]

        monkeypatch.setattr(
            "api.routes.admin.tables.AdminTablesService.get_table",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        # TableItem(extra="allow") preserves the nested shape; the leaf
        # bytes value was decoded before serialization.
        body = response.json()
        nested = body[0]["hardware"]["disks"][0]["path"]
        assert "�" in nested
        assert "/isard/templates/" in nested
        assert ".qcow2" in nested


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
        assert response.status_code == 204
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
        assert response.status_code == 204
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
        assert response.status_code == 204
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
