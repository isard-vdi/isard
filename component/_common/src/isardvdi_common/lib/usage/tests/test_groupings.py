#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``GroupingsUsageProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import groupings as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.GroupingsUsageProcessed,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.GroupingsUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    # Stub the cross-class call into UsageProcessed.get_params so the
    # synthetic-grouping helper has predictable input.
    monkeypatch.setattr(
        mod.UsageProcessed,
        "get_params",
        classmethod(
            lambda cls: {
                "desktop": [
                    {"id": "size", "custom": False},
                    {"id": "custom_x", "custom": True},
                ],
            }
        ),
    )
    yield {"mock_table": mock_table, "Processed": mod.GroupingsUsageProcessed}


class TestListGroupings:
    def test_combines_system_and_user_rows(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [{"id": "user-grp", "item_type": "desktop"}]
        result = stub_rdb["Processed"].list_groupings()
        ids = [g["id"] for g in result]
        assert "_all" in ids
        assert "_system" in ids
        assert "_custom" in ids
        assert "user-grp" in ids


class TestGetGroupingsDropdown:
    def test_shapes_for_dropdown(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.filter.return_value.run.return_value = [
            {"id": "user-grp", "item_type": "desktop"}
        ]
        result = stub_rdb["Processed"].get_groupings_dropdown()
        assert "system" in result and "custom" in result
        assert {g["id"] for g in result["system"]["desktop"]} == {
            "_all",
            "_system",
            "_custom",
        }
        assert result["custom"]["desktop"] == [
            {"id": "user-grp", "item_type": "desktop"}
        ]


class TestGetGrouping:
    def test_returns_user_grouping_when_present(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = {"id": "user-grp"}
        result = stub_rdb["Processed"].get_grouping("user-grp")
        assert result == {"id": "user-grp"}

    def test_falls_back_to_system_grouping(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        result = stub_rdb["Processed"].get_grouping("_all")
        assert result["id"] == "_all"
        assert result["item_type"] == "desktop"

    def test_unknown_id_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].get_grouping("does-not-exist")


class TestNamesById:
    def test_resolves_synthetic_and_user_groupings(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [{"id": "user-grp", "name": "My grouping"}]
        names = stub_rdb["Processed"].names_by_id()
        assert names["_all"] == "All desktop parameters"
        assert names["_system"] == "All desktop system parameters"
        assert names["user-grp"] == "My grouping"

    def test_user_row_wins_over_synthetic_id(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [{"id": "_all", "name": "Shadowed"}]
        assert stub_rdb["Processed"].names_by_id()["_all"] == "Shadowed"

    def test_first_item_type_wins_among_synthetics(self, stub_rdb, monkeypatch):
        """Synthetic ids repeat once per item_type; ``get_grouping`` returns
        the first match, so the name map must agree with it."""
        from isardvdi_common.lib.usage import groupings as mod

        monkeypatch.setattr(
            mod.UsageProcessed,
            "get_params",
            classmethod(
                lambda cls: {
                    "desktop": [{"id": "size", "custom": False}],
                    "media": [{"id": "bytes", "custom": False}],
                }
            ),
        )
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = []
        assert stub_rdb["Processed"].names_by_id()["_all"] == ("All desktop parameters")


class TestCreateGrouping:
    def test_inserts_payload(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.insert.return_value.run.return_value = {"inserted": 1}
        assert (
            stub_rdb["Processed"].create_grouping({"id": "g1", "item_type": "desktop"})
            is True
        )


class TestUpdateGrouping:
    def test_updates_by_id(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.update.return_value.run.return_value = {"replaced": 1}
        assert stub_rdb["Processed"].update_grouping({"id": "g1"}) is True
        chain.get.assert_called_with("g1")


class TestDeleteGrouping:
    def test_deletes_existing(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
        assert stub_rdb["Processed"].delete_grouping("g1") is True

    def test_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 0}
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].delete_grouping("missing")
        assert "missing" in str(exc.value)
