#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.get_resources_config`` and
``Config.set_resources_code`` (tier 3.4 batch 3).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/downloads.py``: the resources block (``url`` /
``code`` / ``private_code``) drives the registration flow with the
updates server.

Pins:
* get_resources_config goes through ``pluck("resources")`` and
  returns ``{}`` when the row or block is missing.
* set_resources_code dispatches a nested update keyed by ``resources.code``
  and clears the get_config cache.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.models import config as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Config, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Config),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    cleared = {"count": 0}
    monkeypatch.setattr(
        mod.Config,
        "clear_get_config_cache",
        classmethod(lambda cls: cleared.update(count=cleared["count"] + 1)),
    )

    yield {"mock_table": mock_table, "Config": mod.Config, "cleared": cleared}


class TestGetResourcesConfig:
    def test_returns_block(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "resources": {
                "url": "https://updates.example.com",
                "code": "reg-token-1",
                "private_code": "private-token-1",
            }
        }
        result = stub_rdb["Config"].get_resources_config()
        assert result["url"] == "https://updates.example.com"
        assert result["code"] == "reg-token-1"
        assert result["private_code"] == "private-token-1"
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        stub_rdb["mock_table"].return_value.get.return_value.pluck.assert_called_with(
            "resources"
        )

    def test_returns_empty_when_resources_missing(self, stub_rdb):
        # Row exists but no resources block — pluck returns an empty
        # dict; the helper folds that to ``{}`` for the caller.
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {}
        assert stub_rdb["Config"].get_resources_config() == {}

    def test_returns_empty_when_row_missing(self, stub_rdb):
        # No config row at all — rdb returns None; the helper folds
        # that to ``{}`` instead of raising.
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = None
        assert stub_rdb["Config"].get_resources_config() == {}


class TestSetResourcesCode:
    def test_persists_string_code(self, stub_rdb):
        stub_rdb["Config"].set_resources_code("new-token")
        stub_rdb["mock_table"].assert_any_call("config")
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"resources": {"code": "new-token"}}

    def test_persists_false_to_revoke(self, stub_rdb):
        # Revocation path — the registry returned 500 so the service
        # marks the stack as no-longer-registered.
        stub_rdb["Config"].set_resources_code(False)
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"resources": {"code": False}}

    def test_clears_cache(self, stub_rdb):
        stub_rdb["Config"].set_resources_code("x")
        assert stub_rdb["cleared"]["count"] == 1
