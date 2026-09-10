#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``GroupsProcessed.get_parent_category_map`` (tier 3.4
batch 2).

Migrated from the inline ``r.table("groups").get_all(...).pluck(...)``
block previously living in apiv4's
``services/admin/users.py:check_group_category``.

Pins:
* Returns ``{group_id: parent_category}`` for the input ids.
* Missing groups are absent from the map (caller raises
  not_found).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.users.groups import groups as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.GroupsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.GroupsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    yield {"mock_table": mock_table, "Processed": mod.GroupsProcessed}


class TestGetParentCategoryMap:
    def test_returns_map(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "g-1", "parent_category": "cat-1"},
            {"id": "g-2", "parent_category": "cat-2"},
        ]
        result = stub_rdb["Processed"].get_parent_category_map(["g-1", "g-2"])
        assert result == {"g-1": "cat-1", "g-2": "cat-2"}

    def test_missing_groups_absent_from_map(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "g-1", "parent_category": "cat-1"},
        ]
        result = stub_rdb["Processed"].get_parent_category_map(["g-1", "g-missing"])
        assert result == {"g-1": "cat-1"}
        assert "g-missing" not in result
