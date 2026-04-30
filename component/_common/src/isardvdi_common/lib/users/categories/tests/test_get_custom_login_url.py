#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``CategoriesProcessed.get_custom_login_url`` (tier 3.4
batch 3 — migrated from apiv4 ``services/categories.py``).

Pins:
* the pluck-on-categories chain returns the row's ``custom_url_name``,
* a missing ``custom_url_name`` field returns ``None``,
* a missing row returns ``None``,
* an underlying rdb exception returns ``None`` (silent — the caller
  treats it as "fall back to /login").
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


class TestGetCustomLoginUrl:
    def test_returns_custom_url_name(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "frontend": True,
            "custom_url_name": "my-tenant",
        }
        assert stub_rdb["Processed"].get_custom_login_url("cat-1") == "my-tenant"
        stub_rdb["mock_table"].assert_any_call("categories")
        stub_rdb["mock_table"].return_value.get.assert_called_with("cat-1")

    def test_returns_none_when_field_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "frontend": True
        }
        assert stub_rdb["Processed"].get_custom_login_url("cat-1") is None

    def test_returns_none_when_row_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_custom_login_url("missing") is None

    def test_returns_none_on_rdb_exception(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.side_effect = RuntimeError(
            "rdb hiccup"
        )
        assert stub_rdb["Processed"].get_custom_login_url("cat-1") is None
