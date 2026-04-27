# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/alloweds.py — search-by-term, update allowed access,
and get allowed-access list for an item.

All three endpoints sit on **token_router** (any authenticated user)
because the manager-side admin UI uses them to populate "who has
access" pickers. Role/category-scoped filtering happens INSIDE the
service via request.token_payload, not at the router gate. These
tests pin that contract: the route forwards the payload, but does
not block any role at the routing layer. A future refactor that
moves these to admin_router would break the manager UI silently.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/allowed/term/{table}
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_TermSearch:
    URL = "/admin/allowed/term/users"

    def test_admin_searches(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["table"] = table
            captured["data"] = data
            captured["role_id"] = payload["role_id"]
            return {"users": [{"id": "u-1"}]}

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"term": "ad"},
        )
        assert response.status_code == 200
        assert captured["table"] == "users"
        assert captured["data"] == {"term": "ad"}
        assert captured["role_id"] == "admin"

    def test_manager_allowed(self, monkeypatch, test_client):
        """Token_router endpoint — managers must succeed; service is
        responsible for category scoping."""
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(lambda t, d, p: {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"term": "ad"},
        )
        assert response.status_code == 200

    def test_user_allowed(self, monkeypatch, test_client):
        """Even basic users can hit this endpoint — the service is
        responsible for role-aware scoping. If a future refactor moves
        this to admin_router, the regular user UI's allowed-picker
        breaks. The test fails loud (200 → 403) when that happens.
        """
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(lambda t, d, p: captured.update(role=p["role_id"]) or {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"term": "ad"},
        )
        assert response.status_code == 200
        assert captured["role"] == "user"

    def test_optional_filters_forwarded_when_set(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["data"] = data
            return {}

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "term": "ad",
                "category": "default",
                "exclude_role": "admin",
                "kind": "isos",
            },
        )
        assert response.status_code == 200
        # exclude_none=True passes set fields through, drops unset ones.
        assert captured["data"]["category"] == "default"
        assert captured["data"]["exclude_role"] == "admin"
        assert captured["data"]["kind"] == "isos"

    def test_missing_term_rejected(self, test_client):
        """term is required by AllowedTermRequest."""
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"category": "default"},
        )
        assert response.status_code in (400, 422)

    def test_typed_error_propagates(self, monkeypatch, test_client):
        def reject(table, data, payload):
            raise Error("forbidden", "Cross-category lookup not allowed")

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"term": "ad"},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/allowed/update/{table}
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_Update:
    URL = "/admin/allowed/update/media"

    def test_admin_updates(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["table"] = table
            captured["data"] = data
            captured["role_id"] = payload["role_id"]

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.update_allowed",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "id": "m-1",
                "allowed": {
                    "roles": ["user"],
                    "categories": [],
                    "groups": [],
                    "users": [],
                },
            },
        )
        assert response.status_code == 200
        assert captured["data"]["id"] == "m-1"
        assert captured["data"]["allowed"]["roles"] == ["user"]

    def test_missing_required_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "m-1"},  # allowed missing
        )
        assert response.status_code in (400, 422)

    def test_unknown_item_returns_404(self, monkeypatch, test_client):
        def fail(table, data, payload):
            raise Error("not_found", "Item not found")

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.update_allowed",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "ghost", "allowed": {}},
        )
        assert response.status_code == 404

    def test_manager_allowed(self, monkeypatch, test_client):
        """Update is on token_router; managers can update allowed lists
        for items in their category. Service enforces the scope."""
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.update_allowed",
            staticmethod(lambda t, d, p: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"id": "m-1", "allowed": {}},
        )
        assert response.status_code == 200

    def test_cross_category_returns_403_from_service(self, monkeypatch, test_client):
        """The route doesn't gate on category — the service does. This
        test pins that a manager trying to touch another category's
        item gets a typed 403 from the service, not a generic 500.
        """

        def reject(table, data, payload):
            raise Error("forbidden", "Item belongs to another category")

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.update_allowed",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"id": "m-x", "allowed": {}},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /allowed/table/{table}
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_GetTable:
    URL = "/allowed/table/media"

    def test_admin_gets_allowed_list(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data):
            captured["table"] = table
            captured["data"] = data
            return {
                "roles": [{"id": "user", "name": "User"}],
                "categories": [],
                "groups": [],
                "users": [],
            }

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_allowed_table",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "m-1"},
        )
        assert response.status_code == 200
        assert captured["data"] == {"id": "m-1"}
        assert response.json()["roles"][0]["id"] == "user"

    def test_unknown_item_returns_404(self, monkeypatch, test_client):
        def fail(table, data):
            raise Error("not_found", "Item not found")

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_allowed_table",
            staticmethod(fail),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "ghost"},
        )
        assert response.status_code == 404

    def test_user_allowed(self, monkeypatch, test_client):
        """token_router endpoint — even users can call (UI needs to
        show whose access is granted). Pin so a future move to
        admin_router fails loud here."""
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_allowed_table",
            staticmethod(lambda t, d: {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"id": "m-1"},
        )
        assert response.status_code == 200
