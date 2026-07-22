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

Update + get-allowed-table additionally enforce per-item ownership
inside the service (``_authorize_table_item``): admin → full; domains
/ media → owner / manager-in-category / advanced-via-deployment /
shared; every other (resource) table → admin only. This restores the
v3 ``@owns_table_item_id`` guard the apiv4 port had dropped (an IDOR
that let any authenticated user rewrite any item's ACL by id).
"""

import pytest
from api.routes.tests.helpers import MockJWT
from api.services.error import Error
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.helpers.error_factory import Error as CommonError

# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/allowed/term/{table}
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_TermSearch:
    URL = "/items/alloweds/term/users"

    def test_admin_searches(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["table"] = table
            captured["data"] = data
            captured["role_id"] = payload["role_id"]
            # Service returns a flat list of pluck'd rows (the webapp
            # iterates with ``$.map``). The route's response_model is
            # ``list[dict]`` to match.
            return [{"id": "u-1", "name": "admin"}]

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

    def test_extra_user_fields_pass_through(self, monkeypatch, test_client):
        """The service plucks ``uid, role, username, category_name,
        group_name`` for the users table; the webapp select2 templates
        render them. ``AllowedTermItem`` must not strip them.
        """
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(
                lambda t, d, p: [
                    {
                        "id": "u-1",
                        "name": "Admin User",
                        "uid": "admin",
                        "role": "admin",
                        "username": "admin",
                        "category_name": "Default",
                        "group_name": "AdminsGroup",
                    }
                ]
            ),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"term": "ad"},
        )
        assert response.status_code == 200
        row = response.json()[0]
        assert row["uid"] == "admin"
        assert row["role"] == "admin"
        assert row["username"] == "admin"
        assert row["category_name"] == "Default"
        assert row["group_name"] == "AdminsGroup"

    def test_manager_allowed(self, monkeypatch, test_client):
        """Token_router endpoint — managers must succeed; service is
        responsible for category scoping."""
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_table_term",
            staticmethod(lambda t, d, p: []),
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
    URL = "/item/allowed/update/media"

    def test_admin_updates(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["table"] = table
            captured["data"] = data
            captured["role_id"] = payload["role_id"]

        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.update_allowed",
            staticmethod(lambda t, d, p, bt: fake(t, d, p)),
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
        assert response.status_code == 204
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
        def fail(table, data, payload, background_tasks):
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
            staticmethod(lambda t, d, p, bt: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body={"id": "m-1", "allowed": {}},
        )
        assert response.status_code == 204

    def test_cross_category_returns_403_from_service(self, monkeypatch, test_client):
        """The route doesn't gate on category — the service does. This
        test pins that a manager trying to touch another category's
        item gets a typed 403 from the service, not a generic 500.
        """

        def reject(table, data, payload, background_tasks):
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
    URL = "/item/allowed/table/media"

    def test_admin_gets_allowed_list(self, monkeypatch, test_client):
        captured = {}

        def fake(table, data, payload):
            captured["table"] = table
            captured["data"] = data
            captured["role_id"] = payload["role_id"]
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
        def fail(table, data, payload):
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
        """token_router endpoint — the route admits any role; the
        service now enforces per-item ownership (admin / owner /
        manager-in-category for domains|media, admin-only otherwise).
        Pin that the routing layer still does not block, so a future
        move to admin_router fails loud here."""
        monkeypatch.setattr(
            "api.routes.admin.alloweds.AdminAllowedsService.get_allowed_table",
            staticmethod(lambda t, d, p: {}),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"id": "m-1"},
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
#  Bastion BackgroundTasks remediation
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_BastionBackgroundTask:
    """Pins the SIGSEGV remediation for ``_common/helpers/alloweds.py:561+606``.

    Previously ``Alloweds.remove_disallowed_bastion_targets_th()`` and
    its sibling ``_target_domains_th()`` fired ``gevent.spawn(...)``;
    under apiv4's asyncio worker the spawned greenlet sat on a libev
    Hub the loop never drives, so the disallowed-target cleanup
    silently never ran. The fix schedules the (now sync) cleanup via
    FastAPI's ``BackgroundTasks``.
    """

    def test_bastion_allowed_schedules_cleanup_after_response(self, monkeypatch):
        from api.services.admin.alloweds import AdminAllowedsService
        from fastapi import BackgroundTasks

        update_args = []
        cleanup_calls = []
        monkeypatch.setattr(
            "api.services.admin.alloweds.Alloweds.update_bastion_alloweds",
            staticmethod(lambda allowed: update_args.append(allowed)),
        )
        monkeypatch.setattr(
            "api.services.admin.alloweds.Alloweds.remove_disallowed_bastion_targets",
            classmethod(lambda cls: cleanup_calls.append("ran") or []),
        )

        bt = BackgroundTasks()
        AdminAllowedsService._update_bastion_allowed(
            {"allowed": {"roles": ["admin"]}},
            {"role_id": "admin"},
            bt,
        )

        # Sync update happens immediately.
        assert update_args == [{"roles": ["admin"]}]
        # Cleanup must be queued (not yet run).
        assert cleanup_calls == []
        assert len(bt.tasks) == 1

        # FastAPI runs ``BackgroundTasks`` after the response. Driving
        # the queue manually proves the registered callable is the
        # cleanup we expected. With the prior gevent.spawn-based
        # ``_th`` wrapper, this assertion would never trigger because
        # the cleanup wasn't registered with the framework at all.
        import asyncio

        asyncio.run(bt())
        assert cleanup_calls == ["ran"]

    def test_bastion_domains_allowed_schedules_cleanup_after_response(
        self, monkeypatch
    ):
        from api.services.admin.alloweds import AdminAllowedsService
        from fastapi import BackgroundTasks

        update_args = []
        cleanup_calls = []
        monkeypatch.setattr(
            "api.services.admin.alloweds.Alloweds.update_bastion_target_domains_alloweds",
            staticmethod(lambda allowed: update_args.append(allowed)),
        )
        monkeypatch.setattr(
            "api.services.admin.alloweds.Alloweds.remove_disallowed_bastion_target_domains",
            classmethod(lambda cls: cleanup_calls.append("ran") or []),
        )

        bt = BackgroundTasks()
        AdminAllowedsService._update_bastion_domains_allowed(
            {"allowed": {"roles": ["admin"]}},
            {"role_id": "admin"},
            bt,
        )

        assert update_args == [{"roles": ["admin"]}]
        assert cleanup_calls == []
        assert len(bt.tasks) == 1

        import asyncio

        asyncio.run(bt())
        assert cleanup_calls == ["ran"]


# ══════════════════════════════════════════════════════════════════════════
#  Ownership guard — _authorize_table_item (IDOR fix)
# ══════════════════════════════════════════════════════════════════════════


class TestAlloweds_AuthorizeTableItem:
    """Unit tests for the per-item ownership guard restored on the
    allowed-update / allowed-table endpoints. Before it, the apiv4 port
    of v3's ``@owns_table_item_id`` was missing — any authenticated user
    could rewrite (or read) the ``allowed`` ACL of any item by id
    (IDOR / privilege escalation).
    """

    @property
    def svc(self):
        from api.services.admin.alloweds import AdminAllowedsService

        return AdminAllowedsService

    def test_admin_bypasses_without_delegating(self, monkeypatch):
        """Admin gets full access and never consults the owns_* checks,
        even for the owner-scoped tables."""
        calls = []
        monkeypatch.setattr(
            "api.services.admin.alloweds.Helpers.owns_domain_id",
            staticmethod(lambda p, i: calls.append("domain") or True),
        )
        monkeypatch.setattr(
            "api.services.admin.alloweds.Helpers.owns_media_id",
            staticmethod(lambda p, i: calls.append("media") or i),
        )
        self.svc._authorize_table_item("reservables_vgpus", "x", {"role_id": "admin"})
        self.svc._authorize_table_item("domains", "d-1", {"role_id": "admin"})
        self.svc._authorize_table_item("media", "m-1", {"role_id": "admin"})
        assert calls == []

    def test_domains_delegates_to_owns_domain_id(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "api.services.admin.alloweds.Helpers.owns_domain_id",
            staticmethod(lambda p, i: seen.update(id=i, role=p["role_id"]) or True),
        )
        self.svc._authorize_table_item(
            "domains", "d-1", {"role_id": "user", "user_id": "u-1"}
        )
        assert seen == {"id": "d-1", "role": "user"}

    def test_media_delegates_to_owns_media_id(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            "api.services.admin.alloweds.Helpers.owns_media_id",
            staticmethod(lambda p, i: seen.update(id=i) or i),
        )
        self.svc._authorize_table_item(
            "media", "m-1", {"role_id": "manager", "category_id": "c1"}
        )
        assert seen == {"id": "m-1"}

    def test_domains_non_owner_propagates_403(self, monkeypatch):
        def deny(p, i):
            raise CommonError("forbidden", "not yours", "")

        monkeypatch.setattr(
            "api.services.admin.alloweds.Helpers.owns_domain_id",
            staticmethod(deny),
        )
        with pytest.raises(ErrorBase) as exc:
            self.svc._authorize_table_item(
                "domains", "d-x", {"role_id": "user", "user_id": "u-1"}
            )
        assert exc.value.status_code == 403

    def test_resource_tables_admin_only(self):
        """Non-ownable resource tables reject any non-admin (incl.
        manager) with a typed 403 — the core IDOR closure."""
        for table in (
            "reservables_vgpus",
            "storage_pool",
            "videos",
            "notifications",
            "bastion",
            "remotevpn",
        ):
            with pytest.raises(ErrorBase) as exc:
                self.svc._authorize_table_item(
                    table, "x", {"role_id": "manager", "category_id": "c1"}
                )
            assert exc.value.status_code == 403, table

    def test_user_cannot_touch_resource_table(self):
        with pytest.raises(ErrorBase) as exc:
            self.svc._authorize_table_item(
                "reservables_vgpus", "x", {"role_id": "user", "user_id": "u-1"}
            )
        assert exc.value.status_code == 403
