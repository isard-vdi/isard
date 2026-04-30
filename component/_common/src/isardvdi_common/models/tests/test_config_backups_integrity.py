#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.get_backups_integrity_enabled`` and
``Config.set_backups_integrity_enabled`` (tier 3.4 batch 2).

Migrated from inline rethink reads/writes previously living in apiv4's
``services/admin/backups.py:get_integrity_enabled / set_integrity_enabled``.

Pins:
* get returns ``None`` when ``backups.integrity_enabled`` is unset (the
  caller substitutes its own deployment-wide default).
* get returns the bool-coerced stored value when present.
* set dispatches the partial update on config[id=1] and clears the
  get_config cache.
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


class TestGetBackupsIntegrityEnabled:
    def test_returns_none_when_unset(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {}
        assert stub_rdb["Config"].get_backups_integrity_enabled() is None

    def test_returns_none_when_no_config_row(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["Config"].get_backups_integrity_enabled() is None

    def test_returns_true_when_set(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "backups": {"integrity_enabled": True}
        }
        assert stub_rdb["Config"].get_backups_integrity_enabled() is True

    def test_returns_false_when_explicitly_off(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "backups": {"integrity_enabled": False}
        }
        assert stub_rdb["Config"].get_backups_integrity_enabled() is False


class TestSetBackupsIntegrityEnabled:
    def test_dispatches_update_and_clears_cache(self, stub_rdb):
        stub_rdb["Config"].set_backups_integrity_enabled(True)
        stub_rdb["mock_table"].assert_any_call("config")
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"backups": {"integrity_enabled": True}}
        assert stub_rdb["cleared"]["count"] == 1
