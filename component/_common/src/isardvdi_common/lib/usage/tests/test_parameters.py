#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ParametersUsageProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import parameters as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ParametersUsageProcessed,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.ParametersUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    yield {"mock_table": mock_table, "Processed": mod.ParametersUsageProcessed}


class TestListParameters:
    def test_returns_all_when_no_ids(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [{"id": "p1"}, {"id": "p2"}]
        result = stub_rdb["Processed"].list_parameters()
        assert result == [{"id": "p1"}, {"id": "p2"}]

    def test_filters_by_ids(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [{"id": "p1"}]
        result = stub_rdb["Processed"].list_parameters(["p1"])
        assert result == [{"id": "p1"}]
        chain.get_all.assert_called_once_with(("ARGS", ["p1"]))


class TestCreateParameter:
    def test_inserts_canonical_payload(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.insert.return_value.run.return_value = {"inserted": 1}
        data = {
            "custom": True,
            "desc": "size of disk",
            "formula": "actual_size",
            "id": "size",
            "item_type": "desktop",
            "name": "Size",
            "units": "GB",
        }
        assert stub_rdb["Processed"].create_parameter(data) is True
        # default 0 is appended automatically.
        chain.insert.assert_called_once_with({**data, "default": 0})


class TestUpdateParameter:
    def test_custom_param_is_updated(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.update.return_value.run.return_value = {"replaced": 1}
        assert (
            stub_rdb["Processed"].update_parameter(
                {"custom": True, "id": "p1", "desc": "x"}
            )
            is True
        )
        chain.get.assert_called_with("p1")

    def test_system_param_raises_forbidden(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].update_parameter({"custom": False, "id": "p1"})
        assert "custom" in str(exc.value).lower()


class TestDeleteParameter:
    def test_deletes_existing(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
        assert stub_rdb["Processed"].delete_parameter("p1") is True

    def test_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 0}
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].delete_parameter("missing")
        assert "missing" in str(exc.value)
