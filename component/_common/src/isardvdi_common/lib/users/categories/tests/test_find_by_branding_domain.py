#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``CategoriesProcessed.find_by_branding_domain`` (tier 3.4 batch 1).

Migrated from the inline filter previously in apiv4's
``services/admin/categories.py:get_logo_by_domain``.

Pins:
* the filter chain runs on the categories table,
* match returns the first row,
* miss returns ``None``,
* underlying exception → ``None`` (silent, by design — the caller
  treats a None as "fall back to default logo").
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


class TestFindByBrandingDomain:
    def test_returns_first_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.limit.return_value.run.return_value = [
            {"id": "cat-1", "name": "Acme"},
        ]
        result = stub_rdb["Processed"].find_by_branding_domain("acme.example")
        assert result == {"id": "cat-1", "name": "Acme"}
        stub_rdb["mock_table"].assert_any_call("categories")

    def test_returns_none_when_no_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.limit.return_value.run.return_value = []
        assert stub_rdb["Processed"].find_by_branding_domain("missing.example") is None

    def test_swallows_runtime_errors(self, stub_rdb):
        """If the rdb query raises (e.g. transient conn drop), return
        None silently — the caller treats this as 'no match', not a 500."""
        stub_rdb[
            "mock_table"
        ].return_value.filter.return_value.limit.return_value.run.side_effect = RuntimeError(
            "transient"
        )
        assert stub_rdb["Processed"].find_by_branding_domain("any.example") is None
