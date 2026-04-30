#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.update_login_notification`` and
``Config.enable_login_notification`` (tier 3.4 batch 1).

Migrated from the inline rethink queries previously living in
apiv4's ``services/admin/login_config.py``. Pins:

* update_login_notification merges new + existing into ``r.literal``
  so unmentioned keys are dropped, falls back ``enabled`` to existing
  DB value when omitted, and returns False on a no-op.
* enable_login_notification dispatches the partial update and clears
  the get_config cache.
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
    monkeypatch.setattr(mod.r, "literal", lambda x: ("LITERAL", x))

    cleared = {"count": 0}
    monkeypatch.setattr(
        mod.Config,
        "clear_get_config_cache",
        classmethod(lambda cls: cleared.update(count=cleared["count"] + 1)),
    )

    yield {"mod": mod, "mock_table": mock_table, "cleared": cleared}


class TestUpdateLoginNotification:
    def test_no_op_when_data_empty(self, stub_rdb):
        """Empty ``data`` means no positions to update — return False, no DB write."""
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.get_field.return_value.default.return_value.run.return_value = {
            "notification_cover": {"enabled": True, "title": "old"},
        }
        assert stub_rdb["mod"].Config.update_login_notification({}) is False

    def test_falls_back_enabled_to_existing(self, stub_rdb):
        """If new payload omits ``enabled``, copy from current DB value."""
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.get_field.return_value.default.return_value.run.return_value = {
            "notification_cover": {"enabled": True, "title": "old"},
        }
        assert (
            stub_rdb["mod"].Config.update_login_notification(
                {"cover": {"title": "new"}}
            )
            is True
        )
        # update was dispatched with enabled=True (carried over) + new title
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        # update_call.args[0] is {"login": ("LITERAL", {...current_with_new...})}
        login_block = update_call.args[0]["login"]
        assert login_block[0] == "LITERAL"
        assert login_block[1]["notification_cover"]["enabled"] is True
        assert login_block[1]["notification_cover"]["title"] == "new"

    def test_clears_cache_on_write(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.get_field.return_value.default.return_value.run.return_value = (
            {}
        )
        stub_rdb["mod"].Config.update_login_notification({"form": {"enabled": False}})
        assert stub_rdb["cleared"]["count"] == 1


class TestEnableLoginNotification:
    def test_dispatches_partial_update(self, stub_rdb):
        stub_rdb["mod"].Config.enable_login_notification("cover", True)
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {
            "login": {"notification_cover": {"enabled": True}}
        }

    def test_clears_cache(self, stub_rdb):
        stub_rdb["mod"].Config.enable_login_notification("form", False)
        assert stub_rdb["cleared"]["count"] == 1
