#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``CreditsUsageProcessed``."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import credits as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.CreditsUsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.CreditsUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.CreditsUsageProcessed, "mod": mod}


WINDOW_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 12, 31, tzinfo=timezone.utc)


class TestListAll:
    def test_returns_credits_with_merged_names(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.merge.return_value.merge.return_value.run.return_value = [
            {"id": "c1", "category_name": "Cat A", "grouping_name": "GroupX"}
        ]
        result = stub_rdb["Processed"].list_all()
        assert result[0]["id"] == "c1"


class TestGetById:
    def test_existing(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = {"id": "c1"}
        assert stub_rdb["Processed"].get_by_id("c1") == {"id": "c1"}

    def test_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].get_by_id("missing")


class TestFindInPeriod:
    def test_no_credits_returns_placeholder(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = []
        result = stub_rdb["Processed"].find_in_period(
            "i1", "category", "g1", WINDOW_START, WINDOW_END
        )
        assert len(result) == 1
        assert result[0]["limits"] is None

    def test_outer_credit_replaces_window(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [
            {
                "id": "c1",
                "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "end_date": datetime(2027, 1, 1, tzinfo=timezone.utc),
                "limits": {"hard": 10},
            }
        ]
        result = stub_rdb["Processed"].find_in_period(
            "i1", "category", "g1", WINDOW_START, WINDOW_END
        )
        assert len(result) == 1
        assert result[0]["limits"] == {"hard": 10}


class TestCreate:
    def test_inserts_per_item_after_validating_limit(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # limit lookup returns a row
        chain.get.return_value.run.return_value = {"id": "l1"}
        # limits pluck returns the limit definition
        chain.get.return_value.pluck.return_value.run.return_value = {
            "id": "l1",
            "name": "n",
            "desc": "d",
            "limits": {"hard": 100},
        }
        # _cut_existing → check_overlapping → no credits in index
        chain.get_all.return_value.run.return_value = []
        chain.insert.return_value.run.return_value = {"inserted": 1}
        data = {
            "item_ids": ["i1", "i2"],
            "item_consumer": "category",
            "item_type": "category",
            "grouping_id": "g1",
            "limit_id": "l1",
        }
        assert stub_rdb["Processed"].create(data, WINDOW_START, WINDOW_END) is True
        assert chain.insert.call_count == 2

    def test_missing_limit_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].create(
                {
                    "item_ids": ["i1"],
                    "item_consumer": "category",
                    "item_type": "category",
                    "grouping_id": "g1",
                    "limit_id": "missing",
                },
                WINDOW_START,
                WINDOW_END,
            )


class TestUpdate:
    def test_missing_credit_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].update("missing", {})

    def test_updates_with_valid_limits(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = {
            "id": "c1",
            "start_date": WINDOW_START,
            "end_date": WINDOW_END,
            "item_id": "i1",
            "item_type": "category",
            "grouping_id": "g1",
        }
        chain.get.return_value.update.return_value.run.return_value = {"replaced": 1}
        new_limits = {"hard": 100, "soft": 80, "exp_max": 60, "exp_min": 20}
        assert stub_rdb["Processed"].update("c1", {"limits": new_limits}) is True


class TestDelete:
    def test_deletes_existing(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
        assert stub_rdb["Processed"].delete("c1") is True

    def test_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 0}
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].delete("missing")


class TestCheckOverlapping:
    def test_no_credits_returns_none(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = []
        result = stub_rdb["Processed"].check_overlapping(
            "i1", "category", "g1", WINDOW_START, WINDOW_END
        )
        assert result is None

    def test_outer_overlap_cuts_to_end_minus_one(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [
            {
                "id": "c1",
                "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "end_date": datetime(2027, 1, 1, tzinfo=timezone.utc),
            }
        ]
        result = stub_rdb["Processed"].check_overlapping(
            "i1", "category", "g1", WINDOW_START, WINDOW_END
        )
        assert result["action"] == "cut"
        assert result["credit_id"] == "c1"

    def test_inner_overlap_returns_deleted(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [
            {
                "id": "c2",
                "start_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "end_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
            }
        ]
        result = stub_rdb["Processed"].check_overlapping(
            "i1", "category", "g1", WINDOW_START, WINDOW_END
        )
        assert result["action"] == "deleted"
        assert result["credit_id"] == "c2"

    def test_skips_self_via_credit_id(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [
            {
                "id": "self",
                "start_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
                "end_date": datetime(2027, 1, 1, tzinfo=timezone.utc),
            }
        ]
        # The outer credit IS the row being updated → must not be flagged.
        result = stub_rdb["Processed"].check_overlapping(
            "i1", "category", "g1", WINDOW_START, WINDOW_END, credit_id="self"
        )
        assert result is None
