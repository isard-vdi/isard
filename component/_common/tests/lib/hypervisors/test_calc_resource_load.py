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

    def test_free_counts_iowait_as_available(self):
        stats = {
            "cpu_5min": {"used": 5.0, "idle": 40.0, "iowait": 55.0},
            "mem_stats": {"total": 0, "used": 0},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["cpu"] == {"total": 100, "used": 5, "free": 95}

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


GIB = 1024 * 1024


class TestRamFreeCountsCommittedMemory:
    """A host that just took a burst looks empty until its guests touch memory."""

    def test_free_is_capped_by_the_memory_guests_can_claim(self):
        stats = {
            "cpu_5min": {"used": 0.0, "idle": 100.0},
            # 504 GiB host, 100 GiB measured in use, 591 GiB promised to guests
            "mem_stats": {
                "total": 504 * GIB,
                "used": 100 * GIB,
                "guests_kb": 591 * GIB,
            },
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["ram"] == {"total": 504 * 1024, "used": 100 * 1024, "free": 0}

    def test_free_is_the_measured_one_when_guests_promise_less(self):
        stats = {
            "cpu_5min": {"used": 0.0, "idle": 100.0},
            "mem_stats": {"total": 64 * GIB, "used": 40 * GIB, "guests_kb": 10 * GIB},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["ram"]["free"] == 24 * 1024

    def test_promised_memory_leaves_the_rest_free(self):
        stats = {
            "cpu_5min": {"used": 0.0, "idle": 100.0},
            "mem_stats": {"total": 64 * GIB, "used": 8 * GIB, "guests_kb": 40 * GIB},
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["ram"]["free"] == 24 * 1024

    def test_hugepage_guests_are_not_counted_twice(self):
        # the pool is already in ``used``: guests on it take nothing more
        stats = {
            "cpu_5min": {"used": 0.0, "idle": 100.0},
            "mem_stats": {
                "total": 64 * GIB,
                "used": 34 * GIB,
                # 32 GiB of guests on the pool plus 8 GiB of regular memory
                "guests_kb": 40 * GIB,
                "hugepages_used_kb": 32 * GIB,
            },
        }

        result = HypervisorsProcessed.calc_resource_load(stats)

        assert result["ram"]["free"] == 24 * 1024

    def test_unknown_guest_memory_keeps_the_measured_free(self):
        for guests in (None, "x", True):
            stats = {
                "cpu_5min": {"used": 0.0, "idle": 100.0},
                "mem_stats": {"total": 64 * GIB, "used": 8 * GIB, "guests_kb": guests},
            }

            result = HypervisorsProcessed.calc_resource_load(stats)

            assert result["ram"]["free"] == 56 * 1024
