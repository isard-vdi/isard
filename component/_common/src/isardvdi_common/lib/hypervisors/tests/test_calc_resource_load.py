#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``HypervisorsProcessed.calc_resource_load``.

Pins the server-side CPU/RAM load derivation that replaced the Go
orchestrator's ``calcLoad``: CPU comes from the 5-minute average
(``used`` rounded up, ``idle`` rounded down, total is always 100) and
RAM from ``mem_stats`` in KB converted to MB with Go-style integer
division (``free`` is ``(total - used) // 1024``, not the difference of
the converted values).
"""

from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed


class TestCalcResourceLoad:
    def test_empty_stats_yield_zero_loads(self):
        result = HypervisorsProcessed.calc_resource_load({})

        assert result == {
            "cpu": {"total": 0, "used": 0, "free": 0},
            "ram": {"total": 0, "used": 0, "free": 0},
        }

    def test_cpu_rounds_used_up_and_idle_down(self):
        stats = {
            "cpu_5min": {"used": 12.3, "idle": 87.7},
            "mem_stats": {"total": 0, "used": 0},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["cpu"] == {"total": 100, "used": 13, "free": 87}

    def test_ram_free_uses_byte_division(self):
        stats = {
            "cpu_5min": {"used": 0.0, "idle": 100.0},
            # 8 GB in KB, with 1 KB free.
            # Without fix: Total/1024 - Used/1024 = 8192-8191 = 1 (wrong).
            # With fix: (Total-Used)/1024 = 1/1024 = 0 (correct).
            "mem_stats": {"total": 8388608, "used": 8388607},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["ram"] == {"total": 8192, "used": 8191, "free": 0}

    def test_full_stats(self):
        stats = {
            "cpu_5min": {"used": 40.2, "idle": 59.8},
            "mem_stats": {"total": 64 * 1024 * 1024, "used": 32 * 1024 * 1024},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result == {
            "cpu": {"total": 100, "used": 41, "free": 59},
            "ram": {"total": 65536, "used": 32768, "free": 32768},
        }
