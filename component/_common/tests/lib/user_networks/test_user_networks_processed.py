#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UserNetworksProcessed`` (tier 3.4 batch 2).

Migrated from the inline ``r.table("user_networks")`` blocks previously
living in apiv4's ``services/user_networks.py``. The service still owns
authorisation (role-scoping); these tests pin only the data-access
layer.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on UserNetworksProcessed so the methods
    run without a real rethinkdb."""
    from isardvdi_common.lib.user_networks import user_networks as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.UserNetworksProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.UserNetworksProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.UserNetworksProcessed}


class TestListAll:
    def test_returns_list_of_rows(self, stub_rdb):
        rows = [{"id": "n1"}, {"id": "n2"}]
        stub_rdb["mock_table"].return_value.run.return_value = rows
        result = stub_rdb["Processed"].list_all()
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("user_networks")

    def test_empty_table_returns_empty_list(self, stub_rdb):
        stub_rdb["mock_table"].return_value.run.return_value = []
        assert stub_rdb["Processed"].list_all() == []


class TestGet:
    def test_returns_row_when_present(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "net-1",
            "name": "n",
        }
        result = stub_rdb["Processed"].get("net-1")
        assert result == {"id": "net-1", "name": "n"}
        stub_rdb["mock_table"].return_value.get.assert_called_with("net-1")

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["Processed"].get("missing-id") is None


class TestExistsByMetadataId:
    def test_true_when_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.limit.return_value.run.return_value = [
            {"id": "net-1"}
        ]
        assert stub_rdb["Processed"].exists_by_metadata_id(123) is True
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            123, index="metadata_id"
        )

    def test_false_when_no_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.limit.return_value.run.return_value = []
        assert stub_rdb["Processed"].exists_by_metadata_id(456) is False


class TestInsert:
    def test_calls_insert(self, stub_rdb):
        network = {"id": "net-1", "name": "n"}
        stub_rdb["Processed"].insert(network)
        stub_rdb["mock_table"].assert_any_call("user_networks")
        stub_rdb["mock_table"].return_value.insert.assert_called_with(network)


class TestUpdate:
    def test_calls_update(self, stub_rdb):
        stub_rdb["Processed"].update("net-1", {"name": "renamed"})
        stub_rdb["mock_table"].return_value.get.assert_called_with("net-1")
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_called_with(
            {"name": "renamed"}
        )


class TestDelete:
    def test_calls_delete(self, stub_rdb):
        stub_rdb["Processed"].delete("net-1")
        stub_rdb["mock_table"].return_value.get.assert_called_with("net-1")
        stub_rdb["mock_table"].return_value.get.return_value.delete.assert_called_once()
