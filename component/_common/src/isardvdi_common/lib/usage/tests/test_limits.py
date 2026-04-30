#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``LimitsUsageProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import limits as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.LimitsUsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.LimitsUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.LimitsUsageProcessed}


VALID_LIMITS = {"hard": 100, "soft": 80, "exp_max": 60, "exp_min": 20}


class TestListLimits:
    def test_returns_all(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [{"id": "l1"}]
        assert stub_rdb["Processed"].list_limits() == [{"id": "l1"}]


class TestCreateLimit:
    def test_inserts_when_limits_valid(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.insert.return_value.run.return_value = {"inserted": 1}
        assert stub_rdb["Processed"].create_limit("n", "d", VALID_LIMITS) is True

    def test_rejects_hard_below_soft(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        bad = {"hard": 10, "soft": 50, "exp_max": 30, "exp_min": 5}
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].create_limit("n", "d", bad)

    def test_rejects_exp_max_not_above_min(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        bad = {"hard": 100, "soft": 80, "exp_max": 5, "exp_min": 20}
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].create_limit("n", "d", bad)


class TestUpdateLimit:
    def test_updates_when_limits_valid(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.update.return_value.run.return_value = {"replaced": 1}
        assert stub_rdb["Processed"].update_limit("l1", "n", "d", VALID_LIMITS) is True
        chain.get.assert_called_with("l1")


class TestDeleteLimit:
    def test_deletes_existing(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
        assert stub_rdb["Processed"].delete_limit("l1") is True

    def test_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 0}
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].delete_limit("missing")
        assert "missing" in str(exc.value)
