#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Config.update_old_tasks`` and
``Config.get_old_tasks_config`` (tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/queues.py``. Note: the apiv4 service used
``r.table("config").update(...)`` (no ``.get(1)``) and
``r.table("config")[0]["old_tasks"]`` (positional index). Both worked
because ``config`` has only one row, but they're imprecise. The new
methods always use ``.get(1)`` for explicit row-by-id semantics.

Pins:
* update_old_tasks dispatches partial update on config[id=1].
* get_old_tasks_config reads via ``.get_field("old_tasks").default({})``,
  returns ``{}`` on rdb error.
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


class TestUpdateOldTasks:
    def test_dispatches_partial_update(self, stub_rdb):
        stub_rdb["Config"].update_old_tasks({"older_than": 86400, "enabled": True})
        stub_rdb["mock_table"].assert_any_call("config")
        stub_rdb["mock_table"].return_value.get.assert_any_call(1)
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {
            "old_tasks": {"older_than": 86400, "enabled": True}
        }

    def test_clears_cache(self, stub_rdb):
        stub_rdb["Config"].update_old_tasks({"enabled": False})
        assert stub_rdb["cleared"]["count"] == 1


class TestGetOldTasksConfig:
    def test_returns_block(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.get_field.return_value.default.return_value.run.return_value = {
            "older_than": 86400,
            "enabled": True,
            "queue_registries": ["finished", "failed"],
        }
        result = stub_rdb["Config"].get_old_tasks_config()
        assert result["older_than"] == 86400
        assert result["enabled"] is True
        assert result["queue_registries"] == ["finished", "failed"]

    def test_returns_empty_on_error(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.get_field.return_value.default.return_value.run.side_effect = RuntimeError(
            "transient"
        )
        assert stub_rdb["Config"].get_old_tasks_config() == {}
