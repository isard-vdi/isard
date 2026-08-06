#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.set_user_migration_config`` (tier 3.4 batch 1).

Migrated from the inline ``r.table("config").get(1).update(...)`` block
previously living in apiv4's ``services/migrations.py``. Pins:

* the update is dispatched against ``config[id=1]``,
* the get_config cache is cleared after the update,
* the post-update ``user_migration`` block is returned.
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

    monkeypatch.setattr(
        mod.Config,
        "get_user_migration_config",
        classmethod(lambda cls: {"enabled": True, "max_per_run": 50}),
    )

    yield {"mock_table": mock_table, "Config": mod.Config, "cleared": cleared}


class TestSetUserMigrationConfig:
    def test_update_dispatched_and_cache_cleared(self, stub_rdb):
        new = {"enabled": True, "max_per_run": 50}
        result = stub_rdb["Config"].set_user_migration_config(new)

        # update was dispatched against config[id=1] with the user_migration key
        stub_rdb["mock_table"].assert_any_call("config")
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_any_call(
            {"user_migration": new}
        )

        # cache invalidator was called
        assert stub_rdb["cleared"]["count"] == 1

        # post-update read returned through
        assert result == new
