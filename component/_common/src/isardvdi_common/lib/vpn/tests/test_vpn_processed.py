#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``VpnProcessed`` (tier 3.4 batch 3).

Migrated from the inline ``r.table(...).get_all(..., index="wg_client_ip")``
blocks previously living in apiv4's ``services/admin/vpn.py``. Service
still owns the three-table branching (users/remotevpn/hypervisors); this
layer pins the rdb shapes only.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on VpnProcessed so the methods run
    without a real rethinkdb."""
    from isardvdi_common.lib.vpn import vpn as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.VpnProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.VpnProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    # r.args is used by reset_connections_for_client_ips; sentinel-tuple
    # makes the assertion in the test readable.
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    yield {"mock_table": mock_table, "Processed": mod.VpnProcessed}


class TestUpdateConnectionByClientIp:
    def test_calls_get_all_then_update(self, stub_rdb):
        connection_data = {"connected": True, "remote_ip": "1.2.3.4", "remote_port": 1}
        stub_rdb["Processed"].update_connection_by_client_ip(
            "users", "10.0.0.1", connection_data
        )
        stub_rdb["mock_table"].assert_any_call("users")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "10.0.0.1", index="wg_client_ip"
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.update.assert_called_with(
            {"vpn": {"wireguard": connection_data}}
        )

    def test_works_for_remotevpn_table(self, stub_rdb):
        connection_data = {"connected": False}
        stub_rdb["Processed"].update_connection_by_client_ip(
            "remotevpn", "10.0.0.2", connection_data
        )
        stub_rdb["mock_table"].assert_any_call("remotevpn")

    def test_works_for_hypervisors_table(self, stub_rdb):
        connection_data = {"connected": True}
        stub_rdb["Processed"].update_connection_by_client_ip(
            "hypervisors", "10.0.0.3", connection_data
        )
        stub_rdb["mock_table"].assert_any_call("hypervisors")


class TestExistsByClientIp:
    def test_true_when_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.limit.return_value.run.return_value = [
            {"id": "row-1"}
        ]
        assert (
            stub_rdb["Processed"].exists_by_client_ip("remotevpn", "10.0.0.1") is True
        )
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "10.0.0.1", index="wg_client_ip"
        )

    def test_false_when_no_hit(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.limit.return_value.run.return_value = []
        assert stub_rdb["Processed"].exists_by_client_ip("users", "10.0.0.99") is False


class TestResetConnectionsForTable:
    def test_calls_has_fields_then_update(self, stub_rdb):
        connection_data = {"connected": False, "remote_ip": None, "remote_port": None}
        stub_rdb["Processed"].reset_connections_for_table("users", connection_data)
        stub_rdb["mock_table"].assert_any_call("users")
        stub_rdb["mock_table"].return_value.has_fields.assert_called_with(
            {"vpn": {"wireguard": "Address"}}
        )
        stub_rdb[
            "mock_table"
        ].return_value.has_fields.return_value.update.assert_called_with(
            {"vpn": {"wireguard": connection_data}}
        )

    def test_works_for_remotevpn(self, stub_rdb):
        stub_rdb["Processed"].reset_connections_for_table("remotevpn", {})
        stub_rdb["mock_table"].assert_any_call("remotevpn")

    def test_works_for_hypervisors(self, stub_rdb):
        stub_rdb["Processed"].reset_connections_for_table("hypervisors", {})
        stub_rdb["mock_table"].assert_any_call("hypervisors")


class TestResetConnectionsForClientIps:
    def test_passes_client_ips_through_args(self, stub_rdb):
        client_ips = ["10.0.0.1", "10.0.0.2"]
        connection_data = {"connected": False}
        stub_rdb["Processed"].reset_connections_for_client_ips(
            "users", client_ips, connection_data
        )
        stub_rdb["mock_table"].assert_any_call("users")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            ("ARGS", client_ips), index="wg_client_ip"
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.update.assert_called_with(
            {"vpn": {"wireguard": connection_data}}
        )

    def test_works_for_hypervisors(self, stub_rdb):
        stub_rdb["Processed"].reset_connections_for_client_ips(
            "hypervisors", ["10.0.0.42"], {}
        )
        stub_rdb["mock_table"].assert_any_call("hypervisors")
