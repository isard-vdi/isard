"""Regression test for ApiHypervisors._prune_card_reservable.

``api_hypervisors`` cannot be imported bare (api/__init__ boots Flask), so -- as
in api_hypervisors_gpu_model_test.py -- we regex-extract ONLY the method source
and exec it with injected fakes for the module globals (app/r/db/log). This pins
the load-bearing orchestration invariants the audit flagged:
  * the SUPPORTED sequence delete_subitem(...) runs BEFORE enable_subitems(...,
    False) -- a reorder would strip the profile from profiles_enabled / delete
    the reservable row before the deassign+booking cleanup ran;
  * the dead-catalog cleanup (_remove_catalog_profile_entry) fires ONLY when the
    reservable row is gone after the disable (last card == no card in the infra
    can realize it), never while it survives.
"""

import os
import re
import types
from unittest import mock

_HERE = os.path.dirname(__file__)
_SRC = os.path.join(_HERE, "api_hypervisors.py")


def _load_prune_fn(survives):
    """Extract _prune_card_reservable, dedent to module level, exec with fakes.

    ``survives`` is what r.table('reservables_vgpus').get(id).run() returns after
    the disable (a row dict == still exists; None == last card, row deleted)."""
    src = open(_SRC).read()
    m = re.search(
        r"\n    def _prune_card_reservable\(self.*?"
        r"\n(?=    def _remove_catalog_profile_entry)",
        src,
        re.S,
    )
    assert m, "could not locate _prune_card_reservable"
    body = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in m.group(0).splitlines()
    )

    class _Ctx:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return False

    run_obj = types.SimpleNamespace(run=lambda *a, **k: survives)
    get_obj = types.SimpleNamespace(get=lambda *a, **k: run_obj)
    ns = {
        "app": types.SimpleNamespace(app_context=lambda: _Ctx()),
        "r": types.SimpleNamespace(table=lambda *a, **k: get_obj),
        "db": types.SimpleNamespace(conn=object()),
        "log": types.SimpleNamespace(
            warning=lambda *a, **k: None, info=lambda *a, **k: None
        ),
    }
    exec(body, ns)
    return ns["_prune_card_reservable"]


def _run(survives):
    fn = _load_prune_fn(survives)
    calls = []
    api_rp = mock.Mock()
    api_rp.delete_subitem.side_effect = lambda *a: calls.append(("delete_subitem", a))
    api_ri = mock.Mock()
    api_ri.enable_subitems.side_effect = lambda *a: calls.append(("enable_subitems", a))
    self_obj = mock.Mock()
    self_obj._remove_catalog_profile_entry.side_effect = lambda *a: calls.append(
        ("remove_catalog", a)
    )
    fn(self_obj, api_ri, api_rp, "A16", "card1", "NVIDIA-A16-4C")
    return calls, self_obj


def test_delete_subitem_runs_before_enable_subitems():
    calls, _ = _run(survives=None)
    names = [c[0] for c in calls]
    assert names.index("delete_subitem") < names.index("enable_subitems")
    assert calls[0] == ("delete_subitem", ("gpus", "card1", "NVIDIA-A16-4C"))
    assert ("enable_subitems", ("gpus", "card1", "NVIDIA-A16-4C", False)) in calls


def test_last_card_removes_catalog_entry():
    # reservable row gone after disable -> last card -> drop the catalog entry
    _, self_obj = _run(survives=None)
    self_obj._remove_catalog_profile_entry.assert_called_once_with(
        "A16", "NVIDIA-A16-4C"
    )


def test_non_last_card_keeps_catalog_entry():
    # reservable still exists -> another card realizes it -> NO catalog removal
    # (total_units is recomputed centrally in enable_subitem, not here)
    _, self_obj = _run(survives={"id": "NVIDIA-A16-4C"})
    self_obj._remove_catalog_profile_entry.assert_not_called()
