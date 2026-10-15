"""Degraded hypervisors are never chosen to start a desktop."""

import importlib.util as _ilu
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

import pytest  # noqa: F401
from tests.helpers import ENGINE_SRC

# stub the parent package so hypervisors.py loads without connecting to RethinkDB
_saved = {
    _m: _sys.modules.get(_m)
    for _m in ("engine.services.db", "engine.services.db.hypervisors", "rethinkdb")
}
_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = []
_pkg.MAX_LEN_PREV_STATUS_HYP = 10
for _name in (
    "cleanup_hypervisor_gpus",
    "close_rethink_connection",
    "new_rethink_connection",
    "rethink_conn",
):
    setattr(_pkg, _name, _MagicMock())
_sys.modules["engine.services.db"] = _pkg
_sys.modules.pop("rethinkdb", None)

_spec = _ilu.spec_from_file_location(
    "engine.services.db.hypervisors",
    str(ENGINE_SRC / "services" / "db" / "hypervisors.py"),
)
mod = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

for _m, _prev in _saved.items():
    if _prev is None:
        _sys.modules.pop(_m, None)
    else:
        _sys.modules[_m] = _prev


def _hyper(hyp_id, degraded=None, **fields):
    row = {
        "id": hyp_id,
        "stats": {"mem_stats": {"total": 100 * 1048576, "available": 90 * 1048576}},
    }
    if degraded is not None:
        row["degraded"] = {"is_degraded": degraded, "reason": "storage: x"}
    row.update(fields)
    return row


class TestFilterDegradedHypers:
    def test_degraded_ones_are_dropped(self):
        ok, bad = _hyper("ok"), _hyper("bad", degraded=True)
        assert mod.filter_degraded_hypers([ok, bad]) == [ok]

    def test_a_recovered_row_counts_as_healthy(self):
        recovered = _hyper("recovered", degraded=False)
        assert mod.filter_degraded_hypers([recovered]) == [recovered]

    def test_a_null_degraded_field_counts_as_healthy(self):
        row = _hyper("old")
        row["degraded"] = None
        assert mod.filter_degraded_hypers([row]) == [row]


class TestPlacement:
    def test_a_degraded_hypervisor_is_not_chosen(self):
        ok, bad = _hyper("ok"), _hyper("bad", degraded=True)
        assert mod.filter_available_hypers([ok, bad]) == [ok]

    def test_all_degraded_means_nowhere_rather_than_a_fallback(self):
        hypers = [_hyper("a", degraded=True), _hyper("b", degraded=True)]
        assert mod.filter_available_hypers(hypers) == []

    def test_a_forced_degraded_hypervisor_is_refused(self):
        hypers = [_hyper("a", degraded=True), _hyper("b")]
        assert mod.filter_available_hypers(hypers, forced_hyp=["a"]) == []

    def test_a_degraded_favourite_falls_back_to_a_healthy_one(self):
        hypers = [_hyper("a", degraded=True), _hyper("b")]
        assert [
            h["id"] for h in mod.filter_available_hypers(hypers, favourite_hyp=["a"])
        ] == ["b"]

    def test_warned_still_beats_degraded(self):
        warned = _hyper("warned", libvirt_warning={"slow_count": 3})
        assert mod.filter_available_hypers([warned, _hyper("bad", degraded=True)]) == [
            warned
        ]
