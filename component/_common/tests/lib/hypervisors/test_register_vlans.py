#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``HypervisorsProcessed.update_hyper_boot_progress`` and
``HypervisorsProcessed.register_vlans`` (tier 3.4 batch 1).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/hypervisors.py``.

Pins:

* update_hyper_boot_progress — partial update of ``boot_progress``
  field, table=hypervisors, get(hyper_id).
* register_vlans — for each vlan, insert into ``interfaces`` with
  ``conflict="update"`` so re-discovery is idempotent. Each insert
  carries the right ``allowed`` defaults (admin-only).
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

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.HypervisorsProcessed}


class TestUpdateHyperBootProgress:
    def test_dispatches_partial_update(self, stub_rdb):
        stub_rdb["Processed"].update_hyper_boot_progress(
            "hyp-1", {"phase": "ready", "pct": 100}
        )
        stub_rdb["mock_table"].assert_any_call("hypervisors")
        stub_rdb["mock_table"].return_value.get.assert_any_call("hyp-1")
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"boot_progress": {"phase": "ready", "pct": 100}}


class TestRegisterVlans:
    def test_inserts_with_conflict_update(self, stub_rdb):
        """Each vlan triggers one ``insert(.., conflict='update')`` on the
        ``interfaces`` table — idempotent re-discovery."""
        stub_rdb["Processed"].register_vlans(["100", "200"])
        # one insert per vlan
        insert_calls = stub_rdb["mock_table"].return_value.insert.call_args_list
        assert len(insert_calls) == 2
        # vlan id and ifname carry the right shape
        first_args, first_kwargs = insert_calls[0]
        first_payload = first_args[0]
        assert first_payload["id"] == "v100"
        assert first_payload["ifname"] == "br-100"
        assert first_payload["kind"] == "bridge"
        # admin-only allowed defaults
        assert first_payload["allowed"]["roles"] == ["admin"]
        assert first_payload["allowed"]["categories"] is False
        # conflict policy
        assert first_kwargs.get("conflict") == "update" or (
            len(first_args) > 1 and first_args[1] == "update"
        )

    def test_empty_input_no_inserts(self, stub_rdb):
        stub_rdb["Processed"].register_vlans([])
        assert stub_rdb["mock_table"].return_value.insert.call_args_list == []
