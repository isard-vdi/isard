#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin recycle-bin cache invalidation on status change.

After restoring a recycle-bin entry the row used to re-appear on
page reload because the list / count caches kept the pre-restore
snapshot for up to 60 seconds. ``Helpers.update_status`` now
eagerly clears every read cache scoped to user/row data, so the
next list query reflects the new ``status`` immediately.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def helper(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # Stub the rdb call inside update_status so it doesn't attempt to
    # acquire a real connection.
    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Helpers),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod.r, "table", MagicMock(name="r.table"))
    yield mod


class TestUpdateStatusInvalidatesCaches:
    def test_clears_item_count_cache(self, helper):
        helper._get_item_count_cache["k1"] = ["row"]
        helper.Helpers.update_status("rb-1", "user-1", "restored")
        assert len(helper._get_item_count_cache) == 0

    def test_clears_count_cache(self, helper):
        helper._get_count_cache["rb-1"] = {"desktops": 1}
        helper.Helpers.update_status("rb-1", "user-1", "restored")
        assert len(helper._get_count_cache) == 0

    def test_clears_user_amount_cache(self, helper):
        helper._get_user_amount_cache["user-1"] = 3
        helper.Helpers.update_status("rb-1", "user-1", "restored")
        assert len(helper._get_user_amount_cache) == 0

    def test_clears_user_recycle_bin_ids_cache(self, helper):
        helper._get_user_recycle_bin_ids_cache["user-1"] = ["rb-1"]
        helper.Helpers.update_status("rb-1", "user-1", "restored")
        assert len(helper._get_user_recycle_bin_ids_cache) == 0

    @pytest.mark.parametrize(
        "status",
        ["restored", "deleting", "deleted", "recycled"],
    )
    def test_clears_for_every_status_transition(self, helper, status):
        helper._get_item_count_cache["k"] = ["row"]
        helper._get_count_cache["rb-1"] = {"desktops": 1}
        helper._get_user_amount_cache["user-1"] = 3
        helper._get_user_recycle_bin_ids_cache["user-1"] = ["rb-1"]
        helper.Helpers.update_status("rb-1", "user-1", status)
        assert len(helper._get_item_count_cache) == 0
        assert len(helper._get_count_cache) == 0
        assert len(helper._get_user_amount_cache) == 0
        assert len(helper._get_user_recycle_bin_ids_cache) == 0


@pytest.fixture
def config_writer(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod, "r", MagicMock(name="r"))
    yield mod


class TestConfigWritesInvalidateTheirCache:
    """Every setter of a cached recycle-bin config value must drop that cache.

    The values are read through a 60 s TTL cache, so a write that leaves the
    cache alone is invisible for up to a minute: an admin flips the setting,
    reloads, and sees the old one.
    """

    def test_default_delete(self, config_writer):
        config_writer._get_default_delete_cache["k"] = "old"
        config_writer.RecycleBin.set_default_delete(True)
        assert len(config_writer._get_default_delete_cache) == 0

    def test_delete_action(self, config_writer):
        config_writer._get_delete_action_cache["k"] = "old"
        config_writer.RecycleBin.set_delete_action("delete")
        assert len(config_writer._get_delete_action_cache) == 0

    def test_old_entries_max_time(self, config_writer):
        config_writer._get_old_entries_config_cache["k"] = {"max_time": 1}
        config_writer.RecycleBin.set_old_entries_max_time(30)
        assert len(config_writer._get_old_entries_config_cache) == 0

    @pytest.mark.parametrize("action", ["delete", "none"])
    def test_old_entries_action_on_both_branches(self, config_writer, action):
        config_writer._get_old_entries_config_cache["k"] = {"action": "old"}
        config_writer.RecycleBin.set_old_entries_action(action)
        assert len(config_writer._get_old_entries_config_cache) == 0
