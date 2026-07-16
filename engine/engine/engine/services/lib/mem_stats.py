# Copyright 2026 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a hypervisor's ``stats.mem_stats``.

Pure, no I/O, so ``engine.models.balancers`` and ``engine.services.db.hypervisors``
can share it without an import cycle (balancers imports db.hypervisors).
"""


def get_hyper_free_ram_kb(hyper):
    """Free RAM (KB) the hypervisor can still grant to guests, hugepages-aware.

    ``set_stats`` writes ``used = total - available - hugepages_free_kb``, and the
    kernel reserves the pool out of MemFree, so ``available`` excludes the whole
    pool (it means "regular, non-hugepage RAM") while ``total - used`` counts the
    idle pool as grantable. Without a pool the two are equal.

    Ask ``ui_actions``'s question instead -- "enough REGULAR ram, or must I back
    this guest with hugepages?" -- and you want the raw ``available``.
    """
    mem_stats = hyper.get("stats", {}).get("mem_stats", {})
    used = mem_stats.get("used")
    if used is None:
        return int(mem_stats.get("available", 0))
    return max(0, int(mem_stats.get("total", 0)) - int(used))
