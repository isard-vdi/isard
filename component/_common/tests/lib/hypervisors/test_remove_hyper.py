#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive path of ``HypervisorsProcessed.remove_hyper``.

Pulling a hypervisor out of the fleet is a one-shot, irreversible operation and
nothing pinned it. These tests fix, on the real ``remove_hyper`` (never mocked):

* the EXACT sequence of writes to the ``hypervisors`` row —
  ``forced_hyp=True`` → ``enabled=False`` → ``status=deleting`` — with
  ``stop_hyper_domains`` interleaved after the first write;
* the engine-removed happy path (row vanishes during the wait → no ``delete``);
* the force-removed path (row survives the wait → a single ``delete``);
* the failure path: when a write raises, it returns the ``Hypervisor not
  found`` dict and does NOT continue mutating the row (no ``enabled`` /
  ``status`` write, no ``delete``);
* the GPU-detach side effect: ``physical_device`` is cleared and each affected
  reservable's ``total_units`` is recomputed.

Only the rethink layer and the collaborators (``stop_hyper_domains``,
``Reservables``, ``time.sleep``) are stubbed; the decisions are the code's.
"""

from unittest.mock import MagicMock, call

import pytest


@pytest.fixture
def stub(monkeypatch):
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
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    # No real sleeping through the 10 s engine wait loop.
    monkeypatch.setattr(mod.time, "sleep", lambda *a, **k: None)
    # stop_hyper_domains reaches DesktopEvents/rethink — spy on it.
    stop = MagicMock(name="stop_hyper_domains")
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "stop_hyper_domains",
        classmethod(lambda cls, hyper_id: stop(hyper_id)),
    )
    # No GPU cards detached by default: the affected-reservables query is empty.
    gpus = router("gpus")
    gpus.filter.return_value.concat_map.return_value.distinct.return_value.run.return_value = (
        []
    )
    gpus.filter.return_value.update.return_value.run.return_value = {}
    return {
        "mod": mod,
        "Cls": mod.HypervisorsProcessed,
        "router": router,
        "tables": tables,
        "stop": stop,
        "monkeypatch": monkeypatch,
    }


def _updates(stub):
    """Ordered list of dicts passed to ``r.table('hypervisors').get(id).update``."""
    hyp = stub["router"]("hypervisors")
    return [c.args[0] for c in hyp.get.return_value.update.call_args_list]


class TestRemoveHyperWriteOrder:
    def test_engine_removed_writes_in_order_and_does_not_delete(self, stub):
        hyp = stub["router"]("hypervisors")
        # The engine deletes the row during the wait loop: first poll returns None.
        hyp.get.return_value.run.return_value = None
        deleting = stub["mod"].HypervisorStatus.deleting.value

        result = stub["Cls"].remove_hyper("hyp-1")

        assert result["status"] is True
        assert result["msg"] == "Hypervisor removed by engine from database"
        # Exact write sequence to the row.
        assert _updates(stub) == [
            {"forced_hyp": True},
            {"enabled": False},
            {"status": deleting},
        ]
        # Domains are stopped once, after forced_hyp is set.
        stub["stop"].assert_called_once_with("hyp-1")
        # The engine removed it, so the worker must NOT delete the row itself.
        hyp.get.return_value.delete.assert_not_called()

    def test_force_removed_deletes_row_when_engine_never_clears_it(self, stub):
        hyp = stub["router"]("hypervisors")
        # Row survives every poll -> the wait loop times out and we delete.
        hyp.get.return_value.run.return_value = {"id": "hyp-1"}
        hyp.get.return_value.delete.return_value.run.return_value = {"deleted": 1}

        result = stub["Cls"].remove_hyper("hyp-1")

        assert result["status"] is True
        assert result["msg"] == "Hypervisor force removed from database"
        # The disable sequence still ran, and then exactly one delete.
        assert _updates(stub) == [
            {"forced_hyp": True},
            {"enabled": False},
            {"status": stub["mod"].HypervisorStatus.deleting.value},
        ]
        hyp.get.return_value.delete.assert_called_once_with()

    def test_write_failure_returns_not_found_and_does_not_half_touch_row(self, stub):
        hyp = stub["router"]("hypervisors")
        # The very first write (forced_hyp) fails.
        hyp.get.return_value.update.return_value.run.side_effect = RuntimeError("boom")

        result = stub["Cls"].remove_hyper("hyp-1")

        assert result == {"status": False, "msg": "Hypervisor not found", "data": {}}
        # Only the first write was attempted; enabled / status were never issued.
        assert _updates(stub) == [{"forced_hyp": True}]
        # And nothing downstream ran: no domain stop after the failed write path
        # short-circuits, no delete.
        hyp.get.return_value.delete.assert_not_called()


class TestRemoveHyperGpuDetach:
    def test_clears_physical_device_and_recomputes_affected_reservables(self, stub):
        from isardvdi_common.lib.bookings import reservables as res_mod

        # Two reservables are backed by this hypervisor's auto GPU cards.
        gpus = stub["router"]("gpus")
        gpus.filter.return_value.concat_map.return_value.distinct.return_value.run.return_value = [
            "NVIDIA-A40-1Q",
            "NVIDIA-A40-2Q",
        ]
        # Capture the Reservables recompute calls without touching the DB.
        fake_ri = MagicMock(name="Reservables-instance")
        stub["monkeypatch"].setattr(
            res_mod, "Reservables", MagicMock(return_value=fake_ri)
        )
        hyp = stub["router"]("hypervisors")
        hyp.get.return_value.run.return_value = None  # engine removes it

        stub["Cls"].remove_hyper("hyp-1")

        # physical_device is detached (not deleted): the card stops counting
        # toward capacity but its profiles_enabled/bookings are untouched.
        gpus.filter.return_value.update.assert_called_once_with(
            {"physical_device": None}
        )
        # Every affected reservable had its total_units recomputed.
        assert fake_ri.recompute_reservable_total_units.call_args_list == [
            call("gpus", "NVIDIA-A40-1Q"),
            call("gpus", "NVIDIA-A40-2Q"),
        ]
