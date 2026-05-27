#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for ``_validate_pluck_safe``
The admin/manager table-list API used to forward the
caller-controlled ``pluck`` query param to RethinkDB unconditionally,
letting an attacker request fields like ``users.vpn`` (WireGuard
keys), ``hypervisors.viewer`` (SSH creds), or ``categories.
authentication`` (LDAP password)."""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.api_admin import _pluck_field_names, _validate_pluck_safe


class TestPluckFieldNames:
    def test_none(self):
        assert _pluck_field_names(None) == []

    def test_string(self):
        assert _pluck_field_names("id") == ["id"]

    def test_list(self):
        assert sorted(_pluck_field_names(["id", "name"])) == ["id", "name"]

    def test_nested_dict(self):
        # ``pluck("vpn", {"wireguard": ["keys"]})`` — the leaf "keys"
        # must be visible to the blocklist regardless of nesting.
        names = _pluck_field_names({"vpn": {"wireguard": ["keys"]}})
        assert "vpn" in names
        assert "wireguard" in names
        assert "keys" in names


class TestValidatePluckSafe:
    def test_none_pluck_allowed(self):
        _validate_pluck_safe("users", None)

    def test_safe_field_allowed_users(self):
        _validate_pluck_safe("users", ["id", "name", "email"])

    def test_password_blocked_universal(self):
        with pytest.raises(Error) as exc:
            _validate_pluck_safe("users", "password")
        assert "password" in str(exc.value)

    def test_api_key_blocked_any_table(self):
        # ``api_key`` lives in the universal blocklist — applies to
        # tables not specifically listed too.
        with pytest.raises(Error):
            _validate_pluck_safe("media", "api_key")

    def test_vpn_blocked_on_users(self):
        with pytest.raises(Error):
            _validate_pluck_safe("users", ["id", "vpn"])

    def test_viewer_blocked_on_hypervisors(self):
        # Shannon's exact reproduction
        with pytest.raises(Error):
            _validate_pluck_safe("hypervisors", "viewer")

    def test_viewer_blocked_on_domains(self):
        with pytest.raises(Error):
            _validate_pluck_safe("domains", ["id", "viewer"])

    def test_categories_authentication_blocked(self):
        with pytest.raises(Error):
            _validate_pluck_safe("categories", "authentication")

    def test_config_table_pluck_denied_entirely(self):
        # ``config`` carries mixed secret material; admin UI never
        # plucks from it normally, so deny everything.
        with pytest.raises(Error):
            _validate_pluck_safe("config", ["id"])

    def test_nested_keys_blocked_via_subkey(self):
        # ``pluck({"vpn": {"wireguard": ["keys"]}})`` — should be
        # blocked because both ``vpn`` (in users-table block) AND
        # ``keys`` (in hypervisors block) appear; on users the
        # ``vpn`` hit fires.
        with pytest.raises(Error):
            _validate_pluck_safe("users", {"vpn": {"wireguard": ["keys"]}})

    def test_keys_blocked_on_hypervisors(self):
        with pytest.raises(Error):
            _validate_pluck_safe("hypervisors", ["id", "keys"])

    def test_safe_fields_pass_other_tables(self):
        # Tables not in the per-table block still get the universal
        # filter, but legit fields pass.
        _validate_pluck_safe("interfaces", ["id", "name", "kind"])
        _validate_pluck_safe("graphics", ["id", "name", "options"])

    def test_error_message_names_offending_fields(self):
        with pytest.raises(Error) as exc:
            _validate_pluck_safe("users", ["id", "password", "api_key"])
        msg = str(exc.value)
        # Both bad fields surfaced in the error so admins debugging
        # 403s know exactly what to remove.
        assert "password" in msg
        assert "api_key" in msg
