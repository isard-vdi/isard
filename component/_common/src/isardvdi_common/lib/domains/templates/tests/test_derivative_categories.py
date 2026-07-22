#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the new ``TemplatesProcessed.list_derivative_categories``
and ``has_cross_category_derivatives`` methods (tier 3.4 batch 3 —
migrated from apiv4 ``services/templates.py``).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.domains.templates import templates as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.TemplatesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.TemplatesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.TemplatesProcessed}


class TestListDerivativeCategories:
    def test_returns_pluck_results(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = [
            {"category": "cat-1"},
            {"category": "cat-2"},
        ]
        result = stub_rdb["Processed"].list_derivative_categories("tpl-1")
        assert result == [{"category": "cat-1"}, {"category": "cat-2"}]
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "tpl-1", index="parents"
        )

    def test_returns_empty_when_no_derivatives(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = []
        assert stub_rdb["Processed"].list_derivative_categories("tpl-1") == []


class TestHasCrossCategoryDerivatives:
    def test_true_when_match(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.filter.return_value.limit.return_value.run.return_value = [
            {"id": "d1", "category": "other"}
        ]
        assert (
            stub_rdb["Processed"].has_cross_category_derivatives("tpl-1", "cat-1")
            is True
        )
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "tpl-1", index="parents"
        )

    def test_false_when_no_match(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.filter.return_value.limit.return_value.run.return_value = (
            []
        )
        assert (
            stub_rdb["Processed"].has_cross_category_derivatives("tpl-1", "cat-1")
            is False
        )
