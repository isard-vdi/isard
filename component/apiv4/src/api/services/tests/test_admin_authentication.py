# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminAuthenticationService providers listing and provider
config updates — pin the wire shape of ``get_providers`` (enabled flag +
global display name per provider) and the pass-through of the ``name``
key in ``update_provider_config``.
"""

from unittest.mock import patch

from api.services.admin.authentication import AdminAuthenticationService


class TestGetProviders:
    @patch("api.services.admin.authentication.Config.get_config")
    def test_includes_global_names(self, mock_get_config):
        mock_get_config.return_value = {
            "auth": {
                "local": {"enabled": True, "local_config": {"name": "nope"}},
                "google": {"enabled": False},
                "saml": {"enabled": True, "saml_config": {"name": "ACME"}},
                "ldap": {"enabled": False, "ldap_config": {}},
            }
        }
        assert AdminAuthenticationService.get_providers() == {
            "local": {"enabled": True},
            "google": {"enabled": False, "name": None},
            "saml": {"enabled": True, "name": "ACME"},
            "ldap": {"enabled": False, "name": None},
        }

    @patch("api.services.admin.authentication.Config.get_config")
    def test_defaults_when_config_is_empty(self, mock_get_config):
        mock_get_config.return_value = None
        assert AdminAuthenticationService.get_providers() == {
            "local": {"enabled": True},
            "google": {"enabled": False, "name": None},
            "saml": {"enabled": False, "name": None},
            "ldap": {"enabled": False, "name": None},
        }


class TestUpdateProviderConfig:
    @patch("api.services.admin.authentication.Caches.clear_config_cache")
    @patch("api.services.admin.authentication.Config.update_provider_config")
    def test_keeps_provider_name(self, mock_update, _mock_clear):
        AdminAuthenticationService.update_provider_config(
            "saml",
            {
                "enabled": True,
                "saml_config": {"name": "ACME", "auto_register_roles": ["a", "b"]},
            },
        )
        data = mock_update.call_args.args[1]
        assert data["saml_config"]["name"] == "ACME"
        assert data["saml_config"]["auto_register_roles"] == "a,b"
