#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``GroupsProcessed.code_search``.

Pins:
* The search only looks at the groups of the given category, through the
  ``parent_category`` index, so a code shared with another category never
  resolves to that other category's group.
* Roles are tried manager → advanced → user, and the first match wins.
* No match in any role raises not_found.
"""

from unittest.mock import MagicMock, call

import pytest
from isardvdi_common.helpers.error_factory import Error


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
    get_all = mock_table.return_value.get_all
    filter_ = get_all.return_value.filter
    yield {
        "get_all": get_all,
        "filter": filter_,
        "run": filter_.return_value.pluck.return_value.limit.return_value.run,
        "Processed": mod.GroupsProcessed,
    }


class TestCodeSearch:
    def test_searches_only_the_given_category(self, stub_rdb):
        stub_rdb["run"].side_effect = [
            iter([]),
            iter([]),
            iter([{"id": "g-1", "parent_category": "cat-1"}]),
        ]

        result = stub_rdb["Processed"].code_search("abc123", "cat-1")

        assert result == {"role_id": "user", "category_id": "cat-1", "group_id": "g-1"}
        assert (
            stub_rdb["get_all"].call_args_list
            == [call("cat-1", index="parent_category")] * 3
        )
        assert stub_rdb["filter"].call_args_list == [
            call({"enrollment": {"manager": "abc123"}}),
            call({"enrollment": {"advanced": "abc123"}}),
            call({"enrollment": {"user": "abc123"}}),
        ]

    def test_first_matching_role_wins(self, stub_rdb):
        stub_rdb["run"].side_effect = [
            iter([{"id": "g-1", "parent_category": "cat-1"}]),
        ]

        result = stub_rdb["Processed"].code_search("abc123", "cat-1")

        assert result == {
            "role_id": "manager",
            "category_id": "cat-1",
            "group_id": "g-1",
        }
        assert stub_rdb["run"].call_count == 1

    def test_raises_not_found_when_no_role_matches(self, stub_rdb):
        stub_rdb["run"].side_effect = [iter([]), iter([]), iter([])]

        with pytest.raises(Error):
            stub_rdb["Processed"].code_search("abc123", "cat-1")

        assert stub_rdb["run"].call_count == 3
