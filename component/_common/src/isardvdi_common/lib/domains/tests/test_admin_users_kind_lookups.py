#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``DomainsProcessed.list_by_kind_user`` and
``DomainsProcessed.list_templates_for_admin`` (tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/users.py:get_user_templates`` /
``get_admin_templates`` / ``get_user_desktops``.

Pins:
* list_by_kind_user uses the ``kind_user`` compound index and plucks
  the requested fields.
* list_templates_for_admin uses the ``kind`` index, applies an
  optional ``{category: category_id}`` filter for managers, and
  plucks the requested fields.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.domains import domains as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DomainsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DomainsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    yield {"mock_table": mock_table, "Processed": mod.DomainsProcessed}


class TestListByKindUser:
    def test_template_lookup_uses_kind_user_index(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "tmpl-1", "name": "T1", "icon": "", "description": ""}
        ]
        result = stub_rdb["Processed"].list_by_kind_user(
            "template", "u-1", ["id", "name", "icon", "description"]
        )
        assert result[0]["id"] == "tmpl-1"
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "kind_user"
        assert get_all_call.args[0] == ["template", "u-1"]

    def test_desktop_lookup_uses_kind_user_index(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = []
        stub_rdb["Processed"].list_by_kind_user(
            "desktop", "u-2", ["id", "name", "status", "icon", "image", "kind"]
        )
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.args[0] == ["desktop", "u-2"]


class TestListTemplatesForAdmin:
    def test_admin_lists_all_templates(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "t-1", "name": "T1", "icon": "", "user": "u-a", "category": "cat-a"}
        ]
        result = stub_rdb["Processed"].list_templates_for_admin(
            ["id", "name", "icon", "user", "category"], category_id=None
        )
        assert result[0]["id"] == "t-1"
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "kind"
        assert get_all_call.args[0] == "template"
        # No filter when admin (category_id is None) — the chain ends
        # with .pluck() directly on get_all().
        stub_rdb["mock_table"].return_value.get_all.return_value.pluck.assert_called()

    def test_manager_filters_by_category(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.pluck.return_value.run.return_value = (
            []
        )
        stub_rdb["Processed"].list_templates_for_admin(
            ["id", "name", "icon"], category_id="cat-1"
        )
        filter_call = stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.call_args
        assert filter_call.args[0] == {"category": "cat-1"}
