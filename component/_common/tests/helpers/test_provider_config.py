# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for provider_config helpers — comma-separated <-> list coercion
for the `auto_register_roles` field. The Go authentication component
stores it as a CSV string; the API needs a JSON list.
"""

from isardvdi_common.helpers.provider_config import (
    provider_config_api_to_db,
    provider_config_db_to_api,
)


class TestDbToApi:
    def test_comma_separated_becomes_list(self):
        config = {"auto_register_roles": "user,advanced,manager"}
        provider_config_db_to_api(config)
        assert config["auto_register_roles"] == ["user", "advanced", "manager"]

    def test_empty_string_becomes_empty_list(self):
        config = {"auto_register_roles": ""}
        provider_config_db_to_api(config)
        assert config["auto_register_roles"] == []

    def test_strips_empty_segments(self):
        # Trailing commas or accidental double commas must not produce
        # blank role names.
        config = {"auto_register_roles": "user,,manager,"}
        provider_config_db_to_api(config)
        assert config["auto_register_roles"] == ["user", "manager"]

    def test_already_list_is_untouched(self):
        config = {"auto_register_roles": ["user"]}
        provider_config_db_to_api(config)
        # Implementation only converts when value is str, so list stays as-is.
        assert config["auto_register_roles"] == ["user"]

    def test_missing_field_is_noop(self):
        config = {"client_id": "abc"}
        provider_config_db_to_api(config)
        assert config == {"client_id": "abc"}

    def test_other_fields_are_not_mangled(self):
        config = {
            "auto_register_roles": "user,admin",
            "client_id": "abc,def",  # literally contains a comma, must stay a string
            "enabled": True,
        }
        provider_config_db_to_api(config)
        assert config["auto_register_roles"] == ["user", "admin"]
        assert config["client_id"] == "abc,def"
        assert config["enabled"] is True


class TestApiToDb:
    def test_list_becomes_comma_separated(self):
        config = {"auto_register_roles": ["user", "advanced"]}
        provider_config_api_to_db(config)
        assert config["auto_register_roles"] == "user,advanced"

    def test_empty_list_becomes_empty_string(self):
        config = {"auto_register_roles": []}
        provider_config_api_to_db(config)
        assert config["auto_register_roles"] == ""

    def test_already_string_is_untouched(self):
        config = {"auto_register_roles": "user,admin"}
        provider_config_api_to_db(config)
        assert config["auto_register_roles"] == "user,admin"

    def test_missing_field_is_noop(self):
        config = {"client_id": "abc"}
        provider_config_api_to_db(config)
        assert config == {"client_id": "abc"}


class TestRoundTrip:
    def test_db_to_api_and_back(self):
        original = "user,advanced,manager"
        config = {"auto_register_roles": original}
        provider_config_db_to_api(config)
        assert isinstance(config["auto_register_roles"], list)
        provider_config_api_to_db(config)
        assert config["auto_register_roles"] == original
