#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``HypervisorsProcessed.set_hyper_only_forced``.

Pins the typed only_forced setter that replaces the orchestrator's generic
``admin/table/update/hypervisors`` write:

* happy path - partial update of ``only_forced`` on the ``hypervisors``
  table, ``get(hyper_id)``, both True and False.
* missing hypervisor - raises ``not_found`` before issuing the update.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


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


class TestSetHyperOnlyForced:
    def test_sets_only_forced_true(self, stub_rdb):
        get = stub_rdb["mock_table"].return_value.get
        get.return_value.run.return_value = {"id": "hyp-1", "only_forced": False}

        stub_rdb["Processed"].set_hyper_only_forced("hyp-1", True)

        stub_rdb["mock_table"].assert_any_call("hypervisors")
        get.assert_any_call("hyp-1")
        update_call = get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"only_forced": True}

    def test_sets_only_forced_false(self, stub_rdb):
        get = stub_rdb["mock_table"].return_value.get
        get.return_value.run.return_value = {"id": "hyp-1", "only_forced": True}

        stub_rdb["Processed"].set_hyper_only_forced("hyp-1", False)

        update_call = get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"only_forced": False}

    def test_raises_not_found_when_missing(self, stub_rdb):
        get = stub_rdb["mock_table"].return_value.get
        get.return_value.run.return_value = None

        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].set_hyper_only_forced("ghost", True)

        assert exc.value.error["error"] == "not_found"
        assert get.return_value.update.call_args_list == []
