#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.get_admin_provider_config`` and
``Config.update_provider_config`` (tier 3.4 batch 2).

Migrated from inline rethink hits previously living in apiv4's
``services/admin/authentication.py:get_provider_config /
update_provider_config``.

Pins:
* get_admin_provider_config raises ``not_found`` when the provider sub-dict
  is missing (rdb's deep ``["auth"][provider]`` traversal raises).
* The template_name lookup mutates ``config["migration"]["notification_bar"]``
  in place.
* update_provider_config dispatches the merge via ``r.row[...].merge(data)``
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
    # r.row needs a stand-in that supports both subscript and merge calls.
    monkeypatch.setattr(mod.r, "row", MagicMock(name="r.row"))

    cleared = {"count": 0}
    monkeypatch.setattr(
        mod.Config,
        "clear_get_config_cache",
        classmethod(lambda cls: cleared.update(count=cleared["count"] + 1)),
    )

    yield {"mock_table": mock_table, "Config": mod.Config, "cleared": cleared}


class TestGetAdminProviderConfig:
    def test_raises_not_found_when_provider_missing(self, stub_rdb):
        # Use ErrorBase directly to avoid the error_factory snapshot-bind
        # race (parallel pytest workers may resolve the lazy ``Error``
        # symbol to different classes depending on whether apiv4 is in
        # sys.modules at the time of the import).
        from isardvdi_common.helpers.error_base import ErrorBase

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.__getitem__.return_value.__getitem__.return_value.run.side_effect = RuntimeError(
            "missing"
        )
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Config"].get_admin_provider_config("saml")
        assert exc.value.error.get("error") == "not_found"

    def test_resolves_template_name(self, stub_rdb):
        provider_cfg = {
            "migration": {
                "notification_bar": {"template": "tpl-1"},
            }
        }
        # First .run() returns the provider config dict.
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.__getitem__.return_value.__getitem__.return_value.run.return_value = (
            provider_cfg
        )
        # Second .run() (notification_tmpls lookup) returns the template name.
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.__getitem__.return_value.run.return_value = (
            "Welcome banner"
        )
        result = stub_rdb["Config"].get_admin_provider_config("saml")
        assert (
            result["migration"]["notification_bar"]["template_name"] == "Welcome banner"
        )


class TestUpdateProviderConfig:
    def test_dispatches_update_and_clears_cache(self, stub_rdb):
        stub_rdb["Config"].update_provider_config("saml", {"client_secret": "x"})
        stub_rdb["mock_table"].assert_any_call("config")
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        # Check that update was called once.
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_called_once()
        assert stub_rdb["cleared"]["count"] == 1
