#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UsersProcessed.list_by_category`` (tier 3.4 batch 2).

Migrated from the inline ``r.table("users").get_all(category_id,
index="category").pluck(...)`` block previously living in apiv4's
``services/admin/users.py:get_category_users``.

Pins:
* Uses the ``category`` secondary index.
* Plucks the admin-summary fields (id, name, username, photo, role,
  group, active).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.users.users import user as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.UsersProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.UsersProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.UsersProcessed}


class TestListByCategory:
    def test_uses_category_index(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {
                "id": "u-1",
                "name": "Alice",
                "username": "alice",
                "photo": "",
                "role": "user",
                "group": "g-1",
                "active": True,
            }
        ]
        result = stub_rdb["Processed"].list_by_category("cat-1")
        assert result[0]["id"] == "u-1"
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "category"
        assert get_all_call.args[0] == "cat-1"

    def test_returns_empty_when_no_users(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = []
        assert stub_rdb["Processed"].list_by_category("empty-cat") == []
