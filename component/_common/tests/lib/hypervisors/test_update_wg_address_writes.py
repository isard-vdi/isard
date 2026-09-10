#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``HypervisorsProcessed.update_wg_address`` must always hit the database.

The wireguard guest IP is reported by the dnsmasq lease hook, which fires
``add``/``old`` for the same lease more than once. Memoizing this method
turned the repeat into a silent no-op: the MAC was not resolved again and the
``domains`` row was not written, so anything that had cleared
``viewer.guest_ip`` in between stayed cleared.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_domain_id_from_wg_mac",
        classmethod(lambda cls, wg_mac: "desktop-1"),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.HypervisorsProcessed}


class TestUpdateWgAddressAlwaysWrites:
    def test_repeated_same_mac_and_ip_writes_every_time(self, stub_rdb):
        get = stub_rdb["mock_table"].return_value.get
        data = {"viewer": {"guest_ip": "192.168.128.76"}}

        first = stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data)
        second = stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data)

        assert first == "desktop-1"
        assert second == "desktop-1"
        assert get.return_value.update.call_count == 2
        assert get.return_value.update.return_value.run.call_count == 2

    def test_mac_is_resolved_again_on_every_call(self, stub_rdb, monkeypatch):
        """The write must target what the MAC resolves to now, not an earlier result."""
        from isardvdi_common.lib.hypervisors import hypervisors as mod

        resolved = iter(["desktop-1", "desktop-2"])
        monkeypatch.setattr(
            mod.Caches,
            "get_domain_id_from_wg_mac",
            classmethod(lambda cls, wg_mac: next(resolved)),
        )
        get = stub_rdb["mock_table"].return_value.get
        data = {"viewer": {"guest_ip": "192.168.128.76"}}

        assert stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data) == (
            "desktop-1"
        )
        assert stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data) == (
            "desktop-2"
        )
        assert [c.args[0] for c in get.call_args_list] == ["desktop-1", "desktop-2"]

    def test_unknown_mac_still_raises_on_a_repeat(self, stub_rdb, monkeypatch):
        """A memoized success must not mask a MAC that no longer resolves.

        ``Caches.get_domain_id_from_wg_mac`` only matches domains in
        Starting/StartingDomainDisposable/Started, so it starts returning None
        as soon as the desktop leaves those states.
        """
        from isardvdi_common.helpers.error_base import ErrorBase
        from isardvdi_common.lib.hypervisors import hypervisors as mod

        resolved = iter(["desktop-1", None])
        monkeypatch.setattr(
            mod.Caches,
            "get_domain_id_from_wg_mac",
            classmethod(lambda cls, wg_mac: next(resolved)),
        )
        data = {"viewer": {"guest_ip": "192.168.128.76"}}

        stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data)
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].update_wg_address("52:54:00:2c:7a:13", data)
