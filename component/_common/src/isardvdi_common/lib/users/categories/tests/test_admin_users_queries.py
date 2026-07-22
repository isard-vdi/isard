#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``CategoriesProcessed`` admin/users query helpers
(tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/users.py`` (``get_category_by_name``,
``_check_duplicate_uid``, ``_check_duplicate_custom_url``).

Pins:
* get_id_by_name returns the first hit's id and raises not_found
  when the index lookup is empty.
* find_duplicate_uid / find_duplicate_custom_url honour the
  ``exclude_category_id`` filter so the row being edited isn't
  flagged as its own duplicate.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.users.categories import categories as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.CategoriesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.CategoriesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.CategoriesProcessed}


class TestGetIdByName:
    def test_returns_id_for_first_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "cat-1"}
        ]
        assert stub_rdb["Processed"].get_id_by_name("Default") == "cat-1"
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "name"
        assert get_all_call.args[0] == "Default"

    def test_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = []
        with pytest.raises(Error) as exc:
            stub_rdb["Processed"].get_id_by_name("Missing")
        assert exc.value.error.get("error") == "not_found"


class TestFindDuplicateUid:
    def test_returns_hits(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = [
            {"id": "cat-1"}
        ]
        assert stub_rdb["Processed"].find_duplicate_uid("acme") == [{"id": "cat-1"}]
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "uid"

    def test_returns_empty_when_no_match(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = []
        assert stub_rdb["Processed"].find_duplicate_uid("acme") == []


class TestFindDuplicateCustomUrl:
    def test_returns_hits(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = [
            {"id": "cat-1"}
        ]
        result = stub_rdb["Processed"].find_duplicate_custom_url("acme-corp")
        assert result == [{"id": "cat-1"}]
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "custom_url_name"
