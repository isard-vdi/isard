# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for per-category branding, authentication, and login notification endpoints."""

import copy
from unittest.mock import MagicMock

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
    """Build a test category with multitenancy fields.

    The default sub-dicts are deep-copied so PUT-style tests that mutate
    nested fields (e.g. ``login_notification.notification_cover.enabled``)
    don't bleed state into later tests via the module-level constants.
    """
    fields = {
        "id": "test-cat",
        "name": "Test Category",
        "uid": "test-cat",
        "branding": copy.deepcopy(_DEFAULT_BRANDING),
        "authentication": copy.deepcopy(_DEFAULT_AUTH),
        "manager_permissions": copy.deepcopy(manager_permissions or _DEFAULT_PERMS),
        "login_notification": copy.deepcopy(_DEFAULT_LOGIN_NOTIFICATION),
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
            url="/admin/item/category/test-cat/branding",
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
            url="/admin/item/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/branding",
            jwt=jwt,
            db_tables_data=_db(manager_permissions={"branding": False}),
        )
        assert response.status_code == 403

    def test_user_role_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="user")
        response = test_client(
            url="/admin/item/category/test-cat/branding",
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
            url="/admin/item/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={"domain": {"enabled": False, "name": "test.example.com"}},
            db_tables_data=_db(),
        )
        assert response.status_code == 204

    def test_manager_without_permission_cannot_update(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={"domain": {"enabled": False}},
            db_tables_data=_db(manager_permissions={"branding": False}),
        )
        assert response.status_code == 403

    def _db_with_branding_on_default(self):
        """`Category.branding` setter validates domain uniqueness via a
        rethinkdb lambda that reads ``cat["branding"]["domain"]["name"]`` on
        every category row. The default ``make_category()`` row lacks a
        ``branding`` field, which crashes the lambda under rethinkdb_mock
        when ``enabled=True`` triggers the uniqueness check. Give every
        category a non-empty branding dict to keep the lambda evaluable.
        """
        return {
            "config": [make_config()],
            "categories": [
                make_category(branding=copy.deepcopy(_DEFAULT_BRANDING)),
                _make_test_category(),
            ],
        }

    def test_surfaces_acme_failure_for_updated_domain(self, test_client, monkeypatch):
        """If haproxy-sync reports an ACME failure on the just-saved domain,
        the response must be 500 carrying the ACME ``detail`` text — silent
        success used to hide DNS-01 / TLS-ALPN misconfigurations from the
        admin (apiv3 commit ``2a2fe04c0``)."""
        from isardvdi_common.helpers import bastion as bastion_mod

        sync_response = MagicMock(name="DomainSyncResponse")
        failure = MagicMock(name="DomainSyncError")
        failure.domain = "custom.example.com"
        failure.error = (
            'acme.sh stderr: {"type":"urn:ietf:params:acme:error:dns",'
            '"detail":"DNS-01 challenge failed for custom.example.com",'
            '"status":400}'
        )
        sync_response.failed_domains = [failure]
        monkeypatch.setattr(
            bastion_mod.Bastion,
            "sync_category_branding_domains",
            classmethod(lambda cls: sync_response),
        )

        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={
                "domain": {
                    "enabled": True,
                    "name": "custom.example.com",
                    "certificate_source": "acme",
                }
            },
            db_tables_data=self._db_with_branding_on_default(),
        )
        assert response.status_code == 500
        body = response.json()
        # ErrorResponse.description carries the human-readable detail.
        # The route's ``Failed to update category branding`` umbrella message
        # may wrap the inner Error; assert on the substring either way.
        haystack = " ".join(str(v) for v in body.values() if isinstance(v, str))
        assert "DNS-01 challenge failed for custom.example.com" in haystack, body

    def test_ignores_acme_failures_on_other_categories(self, test_client, monkeypatch):
        """Failures on a *different* category's domain are not this caller's
        responsibility — the PUT for ``test-cat`` must still succeed."""
        from isardvdi_common.helpers import bastion as bastion_mod

        sync_response = MagicMock(name="DomainSyncResponse")
        unrelated = MagicMock(name="DomainSyncError")
        unrelated.domain = "other.example.com"
        unrelated.error = '{"detail":"unrelated failure"}'
        sync_response.failed_domains = [unrelated]
        monkeypatch.setattr(
            bastion_mod.Bastion,
            "sync_category_branding_domains",
            classmethod(lambda cls: sync_response),
        )

        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/branding",
            method="PUT",
            jwt=jwt,
            body={
                "domain": {
                    "enabled": True,
                    "name": "test.example.com",
                    "certificate_source": "acme",
                }
            },
            db_tables_data=self._db_with_branding_on_default(),
        )
        assert response.status_code == 204, response.text


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/category/{id}/authentication — secret stripping
# ══════════════════════════════════════════════════════════════════════════


class TestGetCategoryAuthentication:
    def test_admin_gets_auth_with_secrets_stripped(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            jwt=jwt,
            db_tables_data=_db(),
        )
        assert response.status_code == 200

    def test_manager_without_auth_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert response.status_code == 204

    def test_manager_with_permission_updates_authentication(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert response.status_code == 204

    def test_manager_without_permission_is_forbidden(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": ""}}),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 204

        get_response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            # google_config is an empty dict: the secret key is absent entirely
            body=self._payload(),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 204

        get_response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": "new-ldap-pass"}}),
            db_tables_data=_db(),
        )
        assert update_response.status_code == 204

        get_response = test_client(
            url="/admin/item/category/test-cat/authentication",
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
            url="/admin/item/category/test-cat/authentication",
            method="PUT",
            jwt=jwt,
            body=self._payload(ldap={"ldap_config": {"password": ""}}),
            db_tables_data=_db(authentication=custom_auth),
        )
        assert response.status_code == 204


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/category/{id}/login_notification
# ══════════════════════════════════════════════════════════════════════════


class TestCategoryLoginNotification:
    def test_admin_updates_login_notification(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/login_notification",
            method="PUT",
            jwt=jwt,
            body={"cover": {"enabled": True, "title": "Updated"}},
            db_tables_data=_db(),
        )
        assert response.status_code == 204

    def test_manager_without_permission_cannot_update(self, test_client):
        jwt = MockJWT(role_id="manager", category_id="test-cat")
        response = test_client(
            url="/admin/item/category/test-cat/login_notification",
            method="PUT",
            jwt=jwt,
            body={"cover": {"enabled": True}},
            db_tables_data=_db(manager_permissions={"login_notification": False}),
        )
        assert response.status_code == 403

    def test_enable_cover_notification(self, test_client):
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/login_notification/cover/enable",
            method="PUT",
            jwt=jwt,
            body={"enabled": True},
            db_tables_data=_db(),
        )
        assert response.status_code == 204

    def test_enable_invalid_type_rejected(self, test_client):
        """Invalid notification type returns 400 (Literal validation)."""
        jwt = MockJWT(role_id="admin")
        response = test_client(
            url="/admin/item/category/test-cat/login_notification/invalid/enable",
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
        """The endpoint returns ``notification_cover`` and
        ``notification_form`` as **lists** so the login page can render
        the global notification and the category-specific one
        side-by-side. With no global notifications and a category that
        defines its own, each list has one item — the category's."""
        response = test_client(
            url="/item/login-config/test-cat",
            db_tables_data=_db(),
        )
        assert response.status_code == 200
        data = response.json()
        # Flat shape — no {"login": {"notification": ...}} wrapper.
        assert "login" not in data
        assert isinstance(data["notification_cover"], list)
        assert data["notification_cover"][0]["enabled"] is False
        assert data["notification_cover"][0]["title"] == "Hello"
        assert isinstance(data["notification_form"], list)
        assert data["notification_form"][0]["enabled"] is True
        assert data["notification_form"][0]["title"] == "Form"

    @pytest.mark.clear_cache
    def test_falls_back_to_global_config(self, test_client):
        """When the category has no ``login_notification``, the merged
        list contains only the global ``Configuration.login`` items
        (each wrapped as a 1-item list)."""
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
        assert "login" not in data
        assert isinstance(data["notification_cover"], list)
        assert data["notification_cover"][0]["enabled"] is False
        assert isinstance(data["notification_form"], list)
        assert data["notification_form"][0]["enabled"] is False

    @pytest.mark.clear_cache
    def test_merges_global_and_category_into_two_item_lists(self, test_client):
        """The actual feature: when *both* a global notification and a
        category notification are set, the response carries a 2-item
        list per slot — global first, then category — so the login page
        renders them stacked. Pin order so a future refactor doesn't
        flip them silently."""
        cat = _make_test_category(
            login_notification={
                "notification_cover": {
                    "enabled": True,
                    "title": "Category-cover",
                },
                "notification_form": {
                    "enabled": True,
                    "title": "Category-form",
                },
            }
        )
        response = test_client(
            url="/item/login-config/test-cat",
            db_tables_data={
                "config": [
                    make_config(
                        login={
                            "notification_cover": {
                                "enabled": True,
                                "title": "Global-cover",
                            },
                            "notification_form": {
                                "enabled": True,
                                "title": "Global-form",
                            },
                        }
                    )
                ],
                "categories": [make_category(), cat],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["notification_cover"], list)
        assert len(data["notification_cover"]) == 2
        # Order: global first, category second — pin so a swap is caught.
        assert data["notification_cover"][0]["title"] == "Global-cover"
        assert data["notification_cover"][1]["title"] == "Category-cover"
        assert isinstance(data["notification_form"], list)
        assert len(data["notification_form"]) == 2
        assert data["notification_form"][0]["title"] == "Global-form"
        assert data["notification_form"][1]["title"] == "Category-form"

    @pytest.mark.clear_cache
    def test_html_unescapes_notification_fields(self, test_client):
        """Title/description and button text/url come out of the DB
        HTML-escaped (``&amp;`` etc.). The endpoint must unescape every
        item in the merged ``notification_cover`` / ``notification_form``
        list so each form pre-fills with the original value the admin
        typed — parity with ``ConfigService.get_login_config`` and
        main's apiv3 ``/api/v3/login_config/<cat>``."""
        cat = _make_test_category(
            login_notification={
                "notification_cover": {
                    "enabled": True,
                    "title": "Cover &amp; Form",
                    "description": "1 &lt; 2",
                    "button": {
                        "text": "Click &quot;here&quot;",
                        "url": "https://example.com/?a=1&amp;b=2",
                    },
                },
                "notification_form": {
                    "enabled": True,
                    "title": "Plain title",
                },
            }
        )
        response = test_client(
            url="/item/login-config/test-cat",
            db_tables_data={
                "config": [make_config()],
                "categories": [make_category(), cat],
            },
        )
        assert response.status_code == 200
        cover = response.json()["notification_cover"][0]
        assert cover["title"] == "Cover & Form"
        assert cover["description"] == "1 < 2"
        assert cover["button"]["text"] == 'Click "here"'
        assert cover["button"]["url"] == "https://example.com/?a=1&b=2"


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


def test_update_branding_does_not_block_on_grpc(test_client):
    """Regression: the PUT /branding endpoint must not wait 30s on an unreachable
    haproxy-sync gRPC service. The autouse bastion-grpc mock in conftest should
    make this call return immediately.
    """
    import time

    jwt = MockJWT(role_id="admin")
    start = time.monotonic()
    response = test_client(
        url="/admin/item/category/test-cat/branding",
        method="PUT",
        jwt=jwt,
        body={"domain": {"enabled": False, "name": "test.example.com"}},
        db_tables_data=_db(),
    )
    elapsed = time.monotonic() - start
    assert response.status_code == 204
    # Production gRPC timeout is 30s; generous 2s ceiling gives plenty of margin
    # on slow CI runners while still catching regressions.
    assert elapsed < 2.0, f"branding PUT took {elapsed:.2f}s — grpc mock not applied?"
