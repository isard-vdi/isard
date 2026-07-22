"""Unit tests for the engine's memory gates on the desktop-placement path.

Needs ``--import-mode=importlib``: prepend mode imports a test module by its
dotted path, which the conftest's stubbed ``engine.services.db`` cannot provide.
"""

import os as _os
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

# Stand in a parent package carrying the names hypervisors.py imports from it, so
# the real module loads on top without engine.services.db.db, which connects to
# RethinkDB at import time (hence the conftest stubbing the package wholesale).
_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = [_os.path.dirname(_os.path.abspath(__file__))]
_pkg.MAX_LEN_PREV_STATUS_HYP = 10
for _name in (
    "cleanup_hypervisor_gpus",
    "close_rethink_connection",
    "new_rethink_connection",
    "rethink_conn",
):
    setattr(_pkg, _name, _MagicMock())
_sys.modules["engine.services.db"] = _pkg
_sys.modules.pop("engine.services.db.hypervisors", None)
# hypervisors.py imports rethinkdb.errors, so it needs the real package (a stub
# is not one). Importing rethinkdb does not connect; only r.connect() does.
_sys.modules.pop("rethinkdb", None)

import pytest  # noqa: E402

import engine.services.db.hypervisors as mod  # noqa: E402

GB = 1024 * 1024  # mem_stats are in KB, so a GB is 1024*1024 of them


def _hyper(hyp_id, total_gb, available_gb, hugepages_free_gb=0, **fields):
    """Row with a coherent mem_stats, mirroring set_stats's
    ``used = total - available - hugepages_free_kb``.
    """
    total, available = total_gb * GB, available_gb * GB
    hp_free = hugepages_free_gb * GB
    row = {
        "id": hyp_id,
        "stats": {
            "mem_stats": {
                "total": total,
                "available": available,
                "used": total - available - hp_free,
                "hugepages_free_kb": hp_free,
            }
        },
    }
    row.update(fields)
    return row


class TestFilterOutOfMemHypers:
    def test_keeps_hugepages_host_whose_pool_covers_the_reserve(self):
        """The regression: raw available is 204G, but 885G of the pool is idle so
        the host can still grant 1089G -- gating on available would evict it.
        """
        hyper = _hyper(
            "hugepages", 1133, 204, hugepages_free_gb=885, min_free_mem_gb=400
        )

        assert mod.filter_outofmem_hypers([hyper]) == [hyper]

    def test_evicts_host_whose_grantable_free_is_below_the_reserve(self):
        hyper = _hyper("plain", 100, 10, min_free_mem_gb=20)

        assert mod.filter_outofmem_hypers([hyper]) == []

    def test_keeps_host_exactly_at_the_reserve(self):
        hyper = _hyper("plain", 100, 20, min_free_mem_gb=20)

        assert mod.filter_outofmem_hypers([hyper]) == [hyper]

    def test_no_reserve_keeps_everything(self):
        # HYPER_FREEMEM defaults to 0, the fleet's usual state.
        hypers = [_hyper("a", 100, 1), _hyper("b", 100, 90)]

        assert mod.filter_outofmem_hypers(hypers) == hypers

    def test_without_hugepages_the_gate_is_unchanged(self):
        # No pool -> used == total - available, so the derived free IS the raw one.
        keep = _hyper("keep", 100, 30, min_free_mem_gb=20)
        drop = _hyper("drop", 100, 10, min_free_mem_gb=20)

        assert mod.filter_outofmem_hypers([keep, drop]) == [keep]

    def test_row_without_used_falls_back_to_available(self):
        # A row whose stats writer has not produced `used` yet (fresh register).
        hyper = {
            "id": "fresh",
            "min_free_mem_gb": 20,
            "stats": {"mem_stats": {"total": 100 * GB, "available": 30 * GB}},
        }

        assert mod.filter_outofmem_hypers([hyper]) == [hyper]


class TestFilterOutOfGPUMemHypers:
    def test_gpu_reserve_counts_the_idle_pool(self, monkeypatch):
        """Gating on the raw available would flip a 900G-pool host to gpu_only over
        memory it has. Two hypers, so the single-hyper early return does not fire.
        """
        # The pass branch only touches the DB when the row is already gpu_only.
        monkeypatch.setattr(
            mod, "new_rethink_connection", lambda: pytest.fail("must not write")
        )
        hugepages = _hyper(
            "hugepages",
            1133,
            204,
            hugepages_free_gb=885,
            min_free_gpu_mem_gb=300,
            min_free_mem_gb=100,
        )
        no_reserve = _hyper("other", 100, 50)

        result = mod.filter_outofGPUmem_hypers([hugepages, no_reserve])

        assert [h["id"] for h in result] == ["hugepages", "other"]
