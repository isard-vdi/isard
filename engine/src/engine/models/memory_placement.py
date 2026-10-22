# Copyright the Isard-vdi project authors:
# License: AGPLv3
"""Memory backing (regular or hugepages) for a non-GPU desktop on one host."""

GIB_KB = 1048576

REGULAR = "regular"
HUGEPAGES = "hugepages"

_HUGEPAGE_SIZES = ((("1", "G"), "1G", 1048576), (("2", "M"), "2M", 2048))


def pick_hugepage_size(memory_kb, hugepages, free_kb):
    """Largest mounted hugepage size that divides the memory and has enough free."""
    memory_kb = round(memory_kb)
    # absent on hypervisors that predate it: any size with a pool stays eligible
    usable = hugepages.get("mount_sizes")
    pool_kb = {
        label: (hugepages.get(label) or {}).get("total", 0) * page_kb
        for _, label, page_kb in _HUGEPAGE_SIZES
    }
    for page, label, page_kb in _HUGEPAGE_SIZES:
        if not pool_kb[label] or memory_kb % page_kb:
            continue
        if usable is not None and label not in usable:
            continue
        # free_kb is summed over all sizes; the other pools bound how much is not ours
        free_of_size_kb = free_kb - sum(v for k, v in pool_kb.items() if k != label)
        if free_of_size_kb >= memory_kb:
            return page
    return None


def committed_regular_kb(mem_stats):
    """Regular memory the running guests can claim, or None when unknown."""
    guests_kb = mem_stats.get("guests_kb")
    if not isinstance(guests_kb, (int, float)) or isinstance(guests_kb, bool):
        return None
    return max(0, int(guests_kb) - int(mem_stats.get("hugepages_used_kb", 0) or 0))


def regular_room_kb(mem_stats, min_free_kb, pending_regular_kb=0):
    """Regular memory a new guest can still take: ``(measured, committed or None)``."""
    measured = (
        int(mem_stats.get("available", 0) or 0) - pending_regular_kb - min_free_kb
    )
    committed = committed_regular_kb(mem_stats)
    if committed is None:
        return measured, None
    regular_total_kb = int(mem_stats.get("total", 0) or 0) - int(
        mem_stats.get("hugepages_total_kb", 0) or 0
    )
    return (
        measured,
        regular_total_kb - min_free_kb - committed - pending_regular_kb,
    )


def plan_memory_backing(
    mem_stats,
    hugepages_info,
    min_free_mem_gb,
    domain_memory_kb,
    pending_regular_kb=0,
    pending_hugepages_kb=0,
):
    """``REGULAR``, ``HUGEPAGES`` or ``None`` when the host has no room for it."""
    if not (hugepages_info or {}).get("mounted"):
        return REGULAR
    mem_stats = mem_stats or {}
    if "available" not in mem_stats:
        # no stats sampled yet: nothing to decide on, start it as before
        return REGULAR
    min_free_kb = int(min_free_mem_gb or 0) * GIB_KB
    measured, committed = regular_room_kb(mem_stats, min_free_kb, pending_regular_kb)
    fits_measured = measured >= domain_memory_kb
    fits_committed = committed is None or committed >= domain_memory_kb
    if fits_measured and fits_committed:
        return REGULAR
    hp_free_kb = int(mem_stats.get("hugepages_free_kb", 0) or 0) - pending_hugepages_kb
    if pick_hugepage_size(domain_memory_kb, hugepages_info, hp_free_kb) is not None:
        return HUGEPAGES
    if fits_measured:
        # committed alone never refuses: hosts without a pool run over-committed too
        return REGULAR
    return None
