# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/authentication.py — policies, providers, force-validate
flags, disclaimer template, provider config (with secret stripping), and
migration exceptions.

The router mixes three FastAPI routers with different auth gates:
    admin_router       (is_admin)            policies, force_validate, provider config, exceptions
    manager_router     (is_admin_or_manager) /admin/authentication/providers
    disclaimer_router  (has_token_disclaimer) /disclaimer

Each test pins the auth gate (admin allowed, manager/user blocked where
appropriate) plus the happy/error path of the underlying service call.

The /authentication/{export,import}/{provider} endpoints used to live
here on token_router and are now exclusively on migration_router in
routes/migrations.py — see test_migrations.py for their coverage.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  Policies (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestPolicyCreate:
    URL = "/admin/item/authentication/policy"

    def _payload(self, **overrides):
        body = {
            "category": "default",
            "role": "admin",
            "type": "local",
            "email_verification": True,
        }
        body.update(overrides)
        return body

    def test_admin_creates_policy(self, monkeypatch, test_client):
        captured = {}

        def fake_add(data):
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(fake_add),
        )

        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 204
        assert captured["data"]["category"] == "default"
        assert captured["data"]["type"] == "local"
        # exclude_none=True drops fields whose value is exactly None,
        # but defaults that are False (email_verification=False) survive.
        assert "disclaimer" not in captured["data"]

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=self._payload(),
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403

    def test_missing_required_field_rejected(self, test_client):
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"category": "default"},  # no role, no type
        )
        assert response.status_code in (400, 422)

    def test_disclaimer_outside_all_categories_returns_400(
        self, monkeypatch, test_client
    ):
        def reject(data):
            raise Error(
                "bad_request",
                "Disclaimer option only available for all categories",
            )

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(disclaimer=True),
        )
        assert response.status_code == 400

    def test_duplicate_policy_returns_409(self, monkeypatch, test_client):
        def conflict(data):
            raise Error("conflict", "Duplicate policy")

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(conflict),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 409

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom(data):
            raise RuntimeError("DB unreachable")

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_policy",
            staticmethod(boom),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 500
        assert response.json().get("error") == "internal_server"


class TestPolicyList:
    URL = "/admin/items/authentication/policies"

    def test_admin_lists_policies(self, monkeypatch, test_client):
        sample = [
            {"id": "p1", "category": "all", "role": "admin", "type": "local"},
            {"id": "p2", "category": "default", "role": "user", "type": "local"},
        ]
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_policies",
            staticmethod(lambda: sample),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_policies",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_disclaimer_template_dict_passes_validation(self, monkeypatch, test_client):
        # Persisted shape when disclaimer is enabled: ``{"template": <id>}``
        # (see webapp/.../users_pwd_policies.js). The response schema must
        # accept it without raising a 500 on Pydantic validation.
        sample = [
            {
                "id": "p1",
                "category": "all",
                "role": "all",
                "type": "local",
                "disclaimer": {"template": "40d07b58-0f25-4137-b67a-749e48579ed7"},
            },
            {"id": "p2", "category": "default", "role": "user", "disclaimer": False},
        ]
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_policies",
            staticmethod(lambda: sample),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        assert body[0]["disclaimer"] == {
            "template": "40d07b58-0f25-4137-b67a-749e48579ed7"
        }
        assert body[1]["disclaimer"] is False


class TestPolicyGet:
    URL = "/admin/item/authentication/policy/p-123"

    def test_admin_gets_policy(self, monkeypatch, test_client):
        captured = {}

        def fake_get(policy_id):
            captured["policy_id"] = policy_id
            return {"id": policy_id, "category": "all", "role": "admin"}

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_policy",
            staticmethod(fake_get),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["policy_id"] == "p-123"
        assert response.json()["id"] == "p-123"

    def test_unknown_policy_returns_404(self, monkeypatch, test_client):
        def not_found(policy_id):
            raise Error("not_found", "Authentication policy not found")

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_policy",
            staticmethod(not_found),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 404


class TestPolicyEdit:
    URL = "/admin/item/authentication/policy/p-123"

    def test_admin_edits_policy(self, monkeypatch, test_client):
        captured = {}

        def fake_edit(policy_id, data):
            captured["policy_id"] = policy_id
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.edit_policy",
            staticmethod(fake_edit),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"role": "manager"},
        )
        assert response.status_code == 204
        assert captured["policy_id"] == "p-123"
        # exclude_none drops the unset Optional fields
        assert captured["data"] == {"role": "manager"}

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.edit_policy",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"role": "manager"},
        )
        assert response.status_code == 403


class TestPolicyDelete:
    URL = "/admin/item/authentication/policy/p-123"

    def test_admin_deletes_policy(self, monkeypatch, test_client):
        captured = {}

        def fake_delete(policy_id):
            captured["policy_id"] = policy_id

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.delete_policy",
            staticmethod(fake_delete),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 204
        assert captured["policy_id"] == "p-123"

    def test_default_policy_delete_returns_403(self, monkeypatch, test_client):
        def reject(policy_id):
            raise Error("forbidden", "Can not delete default permissions")

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.delete_policy",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Providers (manager_router) — managers allowed, users blocked
# ══════════════════════════════════════════════════════════════════════════


class TestProvidersList:
    URL = "/admin/items/authentication/providers"

    def test_admin_lists_providers(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_providers",
            staticmethod(
                lambda: {"local": True, "google": False, "saml": False, "ldap": False}
            ),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["local"] is True

    def test_manager_lists_providers(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_providers",
            staticmethod(lambda: {"local": True}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 200

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_providers",
            staticmethod(lambda: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Force validate at login (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestForceValidate:
    """Three near-identical handlers — pin the field they pass to
    `force_policy_at_login` so a future copy-paste typo is caught.
    """

    def _stub(self, monkeypatch, captured):
        def fake_force(policy_id, field):
            captured["policy_id"] = policy_id
            captured["field"] = field

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.force_policy_at_login",
            staticmethod(fake_force),
        )

    def test_force_email(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/authentication/force_validate/email/p-1",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured == {"policy_id": "p-1", "field": "email_verified"}

    def test_force_disclaimer(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/authentication/force_validate/disclaimer/p-2",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured == {"policy_id": "p-2", "field": "disclaimer_acknowledged"}

    def test_force_password(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/admin/item/authentication/force_validate/password/p-3",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured == {"policy_id": "p-3", "field": "password_last_updated"}

    def test_user_forbidden(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url="/admin/item/authentication/force_validate/email/p-1",
            method="PUT",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Disclaimer (disclaimer_router) — needs disclaimer-typed token
# ══════════════════════════════════════════════════════════════════════════


class TestDisclaimerEndpoint:
    URL = "/disclaimer"

    def test_disclaimer_token_returns_template(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_disclaimer_template",
            staticmethod(
                lambda user_id: {"title": "Welcome", "body": "<p>ok</p>", "footer": ""}
            ),
        )
        response = test_client(
            url=self.URL,
            jwt=MockJWT(token_type="disclaimer-acknowledgement-required"),
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Welcome"

    def test_login_token_rejected(self, monkeypatch, test_client):
        """A regular login token must NOT pass has_token_disclaimer."""
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_disclaimer_template",
            staticmethod(lambda user_id: {}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        # has_token_disclaimer raises Error("forbidden", ...) → 403
        assert response.status_code == 403

    def test_missing_template_returns_404(self, monkeypatch, test_client):
        def not_found(user_id):
            raise Error("not_found", "Unable to find disclaimer template")

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_disclaimer_template",
            staticmethod(not_found),
        )
        response = test_client(
            url=self.URL,
            jwt=MockJWT(token_type="disclaimer-acknowledgement-required"),
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
#  Provider config — admin_router (full CRUD)
#
#  /authentication/{export,import}/{provider} is now exclusively on
#  migration_router (see test_migrations.py) — the token_router copies
#  that lived in admin/authentication.py were dead-code shadows.
# ══════════════════════════════════════════════════════════════════════════


class TestProviderConfig:
    """admin_router CRUD on provider config."""

    def test_admin_gets_provider_config(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_provider_config",
            staticmethod(lambda p: {"migration": {"export": False}}),
        )
        response = test_client(
            url="/admin/item/authentication/provider/google",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        # Note: the GET surface relies on the service to strip secrets;
        # the service test pins that. Here we only assert the wire contract.
        assert "migration" in response.json()

    def test_user_forbidden_on_get(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_provider_config",
            staticmethod(lambda p: {}),
        )
        response = test_client(
            url="/admin/item/authentication/provider/google",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403

    def test_admin_updates_provider_config(self, monkeypatch, test_client):
        captured = {}

        def fake_update(provider, data):
            captured["provider"] = provider
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.update_provider_config",
            staticmethod(fake_update),
        )
        response = test_client(
            url="/admin/item/authentication/provider/google",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "enabled": True,
                "google_config": {"client_id": "x", "client_secret": "y"},
                "migration": {"export": True},
            },
        )
        assert response.status_code == 204
        assert captured["provider"] == "google"
        assert captured["data"]["migration"]["export"] is True
        # extra fields (enabled, <provider>_config) must reach the service,
        # otherwise the global enable/disable toggle never persists.
        assert captured["data"]["enabled"] is True
        assert captured["data"]["google_config"]["client_id"] == "x"

    def test_user_forbidden_on_update(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.update_provider_config",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url="/admin/item/authentication/provider/google",
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Migration exceptions (admin_router)
# ══════════════════════════════════════════════════════════════════════════


class TestMigrationExceptions:
    LIST_URL = "/admin/items/authentication/migrations/exceptions"
    # POST add / DELETE live on the singular sibling under admin_router.
    ITEM_URL = "/admin/item/authentication/migrations/exceptions"

    def test_admin_lists_exceptions(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_migrations_exceptions",
            staticmethod(
                lambda: [{"id": "e1", "item_type": "categories", "item_id": "default"}]
            ),
        )
        response = test_client(url=self.LIST_URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "e1"

    def test_admin_serializes_datetimes_in_list(self, monkeypatch, test_client):
        """The handler converts rethink datetime objects to ISO strings — make
        sure that path doesn't break for naturally serializable rows."""
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_migrations_exceptions",
            staticmethod(lambda: [{"id": "e1", "created_at": "2026-04-27T12:00:00"}]),
        )
        response = test_client(url=self.LIST_URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["created_at"] == "2026-04-27T12:00:00"

    def test_user_forbidden_on_list(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.get_migrations_exceptions",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.LIST_URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_admin_adds_exception(self, monkeypatch, test_client):
        captured = {}

        def fake_add(data):
            captured["data"] = data

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.add_migration_exception",
            staticmethod(fake_add),
        )
        response = test_client(
            url=self.ITEM_URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"item_type": "categories", "item_ids": ["c1", "c2"]},
        )
        assert response.status_code == 204
        assert captured["data"] == {
            "item_type": "categories",
            "item_ids": ["c1", "c2"],
        }

    def test_add_missing_field_rejected(self, test_client):
        response = test_client(
            url=self.ITEM_URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"item_type": "categories"},  # missing item_ids
        )
        assert response.status_code in (400, 422)

    def test_admin_deletes_exception(self, monkeypatch, test_client):
        captured = {}

        def fake_delete(exception_id):
            captured["exception_id"] = exception_id

        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.delete_migration_exception",
            staticmethod(fake_delete),
        )
        response = test_client(
            url=f"{self.ITEM_URL}/e-99",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured["exception_id"] == "e-99"

    def test_user_forbidden_on_delete(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.authentication.AdminAuthenticationService.delete_migration_exception",
            staticmethod(lambda eid: None),
        )
        response = test_client(
            url=f"{self.ITEM_URL}/e-99",
            method="DELETE",
            jwt=MockJWT(role_id="user"),
        )
        assert response.status_code == 403
