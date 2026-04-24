# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for per-category branding, authentication, and login notification endpoints."""

import pytest
from api.routes.tests.factories import make_category, make_config
from api.routes.tests.helpers import MockJWT

_DEFAULT_AUTH = {
    "local": {
        "config_source": "global",
        "disabled": False,
        "email_domain_restriction": {"enabled": False, "allowed": []},
    },
    "ldap": {
        "config_source": "global",
        "disabled": True,
        "email_domain_restriction": {"enabled": False, "allowed": []},
        "ldap_config": {"password": "secret123"},
    },
    "google": {
        "config_source": "global",
        "disabled": True,
        "email_domain_restriction": {"enabled": False, "allowed": []},
        "google_config": {"client_secret": "google-secret"},
    },
    "saml": {
        "config_source": "global",
        "disabled": True,
        "email_domain_restriction": {"enabled": False, "allowed": []},
    },
}

_DEFAULT_BRANDING = {
    "domain": {"enabled": False, "name": ""},
    "logo": {"enabled": False},
}

_DEFAULT_PERMS = {
    "authentication": True,
    "branding": True,
    "login_notification": True,
}

_DEFAULT_LOGIN_NOTIFICATION = {
    "notification_cover": {"enabled": False, "title": "Hello"},
    "notification_form": {"enabled": True, "title": "Form"},
}


def _make_test_category(manager_permissions=None, **extra):
    """Build a test category with multitenancy fields."""
    fields = {
        "id": "test-cat",
        "name": "Test Category",
        "uid": "test-cat",
        "branding": _DEFAULT_BRANDING,
        "authentication": _DEFAULT_AUTH,
        "manager_permissions": manager_permissions or _DEFAULT_PERMS,
        "login_notification": _DEFAULT_LOGIN_NOTIFICATION,
    }
    fields.update(extra)
    return make_category(**fields)


def _db(**extra_fields):
    return {
        "config": [make_config()],
        "categories": [make_category(), _make_test_category(**extra_fields)],
    }


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/category/{id}/branding
# ══════════════════════════════════════════════════════════════════════════


class TestGetCategoryBranding:
    def test_admin_gets_branding(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "domain" in data
        assert data["domain"]["enabled"] is False

    def test_manager_with_permission_gets_branding(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(manager_permissions={"branding": False}),
        )
        assert response.status_code == 403

    def test_user_role_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="user")
        response = test_client(
            url="/admin/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(),
        )
        # manager_router rejects user role with 403
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/category/{id}/branding
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateCategoryBranding:
    def test_admin_updates_branding(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={"domain": {"enabled": False, "name": "test.example.com"}},
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_permission_cannot_update(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={"domain": {"enabled": False}},
            db_tables_data=_db(manager_permissions={"branding": False}),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/category/{id}/authentication — secret stripping
# ══════════════════════════════════════════════════════════════════════════


class TestGetCategoryAuthentication:
    def test_admin_gets_auth_with_secrets_stripped(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200
        data = response.json()

        # LDAP password should be stripped, replaced by password_set
        ldap = data.get("ldap", {})
        ldap_config = ldap.get("ldap_config", {})
        assert "password" not in ldap_config
        assert ldap_config.get("password_set") is True

        # Google client_secret should be stripped
        google = data.get("google", {})
        google_config = google.get("google_config", {})
        assert "client_secret" not in google_config
        assert google_config.get("client_secret_set") is True

    def test_manager_with_permission_gets_auth(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_auth_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(manager_permissions={"authentication": False}),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/category/{id}/authentication — permissions + secret preservation
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateCategoryAuthentication:
    """Covers the admin-only / missing-secret-preservation behaviour of the
    multitenancy handler.
    """

    def _payload(self, **overrides):
        """Build a minimal valid authentication payload with overrides applied."""
        auth = {
            "local": {
                "config_source": "global",
                "disabled": False,
                "email_domain_restriction": {"enabled": False, "allowed": []},
            },
            "ldap": {
                "config_source": "global",
                "disabled": True,
                "email_domain_restriction": {"enabled": False, "allowed": []},
                "ldap_config": {},
            },
            "google": {
                "config_source": "global",
                "disabled": True,
                "email_domain_restriction": {"enabled": False, "allowed": []},
                "google_config": {},
            },
            "saml": {
                "config_source": "global",
                "disabled": True,
                "email_domain_restriction": {"enabled": False, "allowed": []},
            },
        }
        for provider, cfg in overrides.items():
            auth[provider].update(cfg)
        return {"authentication": auth}

    # ── permissions ──────────────────────────────────────────────────────

    def test_admin_updates_authentication(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_with_permission_updates_authentication(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(manager_permissions={"authentication": False}),
        )
        assert response.status_code == 403

    def test_manager_with_missing_permission_key_is_forbidden(self, test_client):
        """Fail-closed: a manager_permissions dict that omits the `authentication`
        key entirely must also be rejected, not silently allowed."""
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(
                manager_permissions={"branding": True, "login_notification": True}
            ),
        )
        assert response.status_code == 403

    def test_user_role_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="user")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert response.status_code == 403

    # ── schema validation ───────────────────────────────────────────────

    def test_invalid_payload_rejected(self, test_client):
        """Payload without the required `authentication` top-level key is rejected."""
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body={"wrong_field": {}},
            db_tables_data=_db(),
        )
        # Pydantic validation error → 422 (or 400 depending on FastAPI config)
        assert response.status_code in (400, 422)

    # ── secret preservation (the core of the CRIT-1 fix) ────────────────

    def test_secret_preserved_when_payload_sends_empty_password(self, test_client):
        """PUT with an empty ldap password must keep the existing one in DB."""
        jwt = MockJWT(role_id="admin")
        update_response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": ""}}),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 200

        get_response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert get_response.status_code == 200
        ldap_config = get_response.json().get("ldap", {}).get("ldap_config", {})
        assert "password" not in ldap_config, "raw password must not leak on GET"
        assert (
            ldap_config.get("password_set") is True
        ), "existing ldap password must survive an update that sends an empty value"

    def test_secret_preserved_when_payload_omits_client_secret(self, test_client):
        """PUT without the google client_secret key must keep the existing one."""
        jwt = MockJWT(role_id="admin")
        update_response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            # google_config is an empty dict: the secret key is absent entirely
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 200

        get_response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert get_response.status_code == 200
        google_config = get_response.json().get("google", {}).get("google_config", {})
        assert "client_secret" not in google_config
        assert (
            google_config.get("client_secret_set") is True
        ), "existing google client_secret must survive an update that omits the key"

    def test_secret_updated_when_payload_provides_new_password(self, test_client):
        """PUT with a new non-empty ldap password is accepted and the field remains set."""
        jwt = MockJWT(role_id="admin")
        update_response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": "new-ldap-pass"}}),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 200

        get_response = test_client(
            url="/admin/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert get_response.status_code == 200
        ldap_config = get_response.json().get("ldap", {}).get("ldap_config", {})
        assert ldap_config.get("password_set") is True

    def test_empty_secret_on_empty_existing_does_not_raise(self, test_client):
        """Starting with no existing secret and sending an empty secret is a no-op,
        not an error — the field should simply not be written."""
        jwt = MockJWT(role_id="admin")
        # DB with an empty ldap_config (no existing password)
        custom_auth = {
            "local": _DEFAULT_AUTH["local"],
            "ldap": {
                "config_source": "global",
                "disabled": True,
                "email_domain_restriction": {"enabled": False, "allowed": []},
                "ldap_config": {},  # no password
            },
            "google": _DEFAULT_AUTH["google"],
            "saml": _DEFAULT_AUTH["saml"],
        }
        response = test_client(
            url="/admin/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": ""}}),
            db_tables_data=_db(authentication=custom_auth),
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/category/{id}/login_notification
# ══════════════════════════════════════════════════════════════════════════


class TestCategoryLoginNotification:
    def test_admin_updates_login_notification(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/login_notification",
            method="PUT",
            jwt=jwt,
            body={"cover": {"enabled": True, "title": "Updated"}},
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_permission_cannot_update(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/category/test-cat/login_notification",
            method="PUT",
            jwt=jwt,
            body={"cover": {"enabled": True}},
            db_tables_data=_db(manager_permissions={"login_notification": False}),
        )
        assert response.status_code == 403

    def test_enable_cover_notification(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/login_notification/cover/enable",
            method="PUT",
            jwt=jwt,
            body={"enabled": True},
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_enable_invalid_type_rejected(self, test_client):
        """Invalid notification type returns 400 (Literal validation)."""
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/category/test-cat/login_notification/invalid/enable",
            method="PUT",
            jwt=jwt,
            body={"enabled": True},
            db_tables_data=_db(),
        )
        # FastAPI returns 422 for Pydantic validation errors on path params
        assert response.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════════
#  GET /item/login-config/{category_id} — public endpoint
# ══════════════════════════════════════════════════════════════════════════


class TestLoginConfigByCategory:
    @pytest.mark.clear_cache
    def test_returns_category_login_notification(self, test_client):
        response = test_client(
            url="/item/login-config/test-cat",
            db_tables_data=_db(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "login" in data

    @pytest.mark.clear_cache
    def test_falls_back_to_global_config(self, test_client):
        cat = _make_test_category()
        cat.pop("login_notification", None)
        response = test_client(
            url="/item/login-config/test-cat",
            db_tables_data={
                "config": [
                    make_config(
                        login={
                            "notification_cover": {"enabled": False},
                            "notification_form": {"enabled": False},
                        }
                    )
                ],
                "categories": [make_category(), cat],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "login" in data


# ══════════════════════════════════════════════════════════════════════════
#  GET /logo — public endpoint
# ══════════════════════════════════════════════════════════════════════════


class TestLogoEndpoint:
    @pytest.mark.clear_cache
    def test_returns_404_when_no_logo(self, test_client):
        response = test_client(
            url="/logo",
            db_tables_data=_db(),
        )
        # No branding domain match, no default logo file → 404
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
#  /logo direct endpoint
# ══════════════════════════════════════════════════════════════════════════


class TestLogoEndpointDirect:
    def test_logo_endpoint_accessible(self, client):
        response = client.get("/api/v4/logo", follow_redirects=False)
        # Direct open_router endpoint, returns 404 (no logo configured)
        assert response.status_code in (200, 404)
