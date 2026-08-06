"""Regression test for HypervisorsProcessed._prune_card_reservable.

Port of api/src/api/libv2/api_hypervisors_gpu_prune_test.py (upstream MR
!4496). The method is a ``@classmethod``, so its underlying function is bound
to a mock receiver standing in for ``cls`` and the module-level ``r`` is
stubbed. This pins the load-bearing orchestration invariants the audit flagged:
  * the SUPPORTED sequence delete_subitem(...) runs BEFORE enable_subitems(...,
    False) -- a reorder would strip the profile from profiles_enabled / delete
    the reservable row before the deassign+booking cleanup ran;
  * the dead-catalog cleanup (_remove_catalog_profile_entry) fires ONLY when the
    reservable row is gone after the disable (last card == no card in the infra
    can realize it), never while it survives.
"""

import types
from unittest import mock

from isardvdi_common.lib.hypervisors import hypervisors
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed

_prune_card_reservable = HypervisorsProcessed._prune_card_reservable.__func__


def _run(survives):
    """Run the guard with a stubbed rdb.

    ``survives`` is what r.table('reservables_vgpus').get(id).run() returns after
    the disable (a row dict == still exists; None == last card, row deleted)."""
    calls = []
    api_rp = mock.Mock()
    api_rp.delete_subitem.side_effect = lambda *a: calls.append(("delete_subitem", a))
    api_ri = mock.Mock()
    api_ri.enable_subitems.side_effect = lambda *a: calls.append(("enable_subitems", a))
    # The receiver stands in for ``cls``: it provides _rdb_context (a context
    # manager), _rdb_connection and _remove_catalog_profile_entry.
    cls_obj = mock.MagicMock()
    cls_obj._remove_catalog_profile_entry.side_effect = lambda *a: calls.append(
        ("remove_catalog", a)
    )
    run_obj = types.SimpleNamespace(run=lambda *a, **k: survives)
    get_obj = types.SimpleNamespace(get=lambda *a, **k: run_obj)
    stub_r = types.SimpleNamespace(table=lambda *a, **k: get_obj)
    with mock.patch.object(hypervisors, "r", stub_r):
        _prune_card_reservable(cls_obj, api_ri, api_rp, "A16", "card1", "NVIDIA-A16-4C")
    return calls, cls_obj


def test_delete_subitem_runs_before_enable_subitems():
    calls, _ = _run(survives=None)
    names = [c[0] for c in calls]
    assert names.index("delete_subitem") < names.index("enable_subitems")
    assert calls[0] == ("delete_subitem", ("gpus", "card1", "NVIDIA-A16-4C"))
    assert ("enable_subitems", ("gpus", "card1", "NVIDIA-A16-4C", False)) in calls


def test_last_card_removes_catalog_entry():
    # reservable row gone after disable -> last card -> drop the catalog entry
    _, cls_obj = _run(survives=None)
    cls_obj._remove_catalog_profile_entry.assert_called_once_with(
        "A16", "NVIDIA-A16-4C"
    )


def test_non_last_card_keeps_catalog_entry():
    # reservable still exists -> another card realizes it -> NO catalog removal
    # (total_units is recomputed centrally in enable_subitem, not here)
    _, cls_obj = _run(survives={"id": "NVIDIA-A16-4C"})
    cls_obj._remove_catalog_profile_entry.assert_not_called()
