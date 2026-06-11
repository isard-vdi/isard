# Copyright the Isard-vdi project authors:
# License: AGPLv3
"""Tier-1 NUMA-node balancing for non-GPU desktops.

Pure, dependency-free helpers (no DB, no config import) so they are unit-testable
in isolation. The stateful piece (per-node in-flight "pending" accounting) lives
on ``BalancerInterface`` in ``balancers.py`` and delegates the maths here.

Why this exists
---------------
On a 2-NUMA-node hypervisor the engine pins each desktop's vCPUs (and, for GPU /
low-RAM desktops, its 1 GiB hugepage memory) to one node. The previous non-GPU
node pick was ``max(numa_hugepages_free_kb)`` — but a non-GPU desktop does not
consume hugepages, so that figure barely moves between starts and **every**
non-GPU desktop landed on the same node (the one with marginally more free
pages). This module spreads them: it scores each node by the resource it is
shortest on (memory headroom vs vCPU headroom) after subtracting the desktops
already in flight, so consecutive starts alternate nodes.

Limitation (Tier-2 follow-up): with no per-node *committed* load signal from
libvirt, ongoing balance beyond the pending-expiry window relies on the per-node
free-hugepage figure. Spreading is strongest during start bursts (class
launches), which is exactly when piling hurts most.
"""

# 1 GiB expressed in KiB — the unit numa_hugepages_free_kb / domain memory use.
_GIB_KB = 1048576


def _cpulist_size(cpulist):
    """Count CPUs in a libvirt cpulist string like ``"0-47,90-91"``."""
    if not cpulist:
        return 0
    total = 0
    for part in str(cpulist).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                total += int(hi) - int(lo) + 1
            except ValueError:
                continue
        else:
            try:
                int(part)
            except ValueError:
                continue
            total += 1
    return total


def aggregate_pending_by_node(entries, now, expiry_seconds):
    """Sum still-live per-node pending starts.

    ``entries`` is a list of ``(node, ram_gb, vcpus, timestamp)`` tuples; entries
    older than ``expiry_seconds`` are ignored (the start either completed and is
    now reflected in stats, or it failed). Returns
    ``{node: {"ram_kb": int, "vcpus": int}}``.
    """
    cutoff = now - expiry_seconds
    result = {}
    for node, ram_gb, vcpus, ts in entries:
        if ts <= cutoff:
            continue
        bucket = result.setdefault(str(node), {"ram_kb": 0, "vcpus": 0})
        bucket["ram_kb"] += ram_gb * _GIB_KB
        bucket["vcpus"] += vcpus
    return result


def select_balanced_numa_node(
    numa_topology,
    numa_hugepages_free_kb,
    domain_memory_kb,
    domain_vcpus,
    pending_by_node,
):
    """Pick the least-loaded NUMA node for a non-GPU desktop, or ``None``.

    Returns ``None`` when there is nothing to balance (fewer than two nodes or no
    topology), so the caller keeps its existing single-node behaviour.

    For each node we compute headroom *after* placing this desktop, as a fraction
    of the node's capacity, for both memory (per-node free hugepages, the only
    per-node memory signal available) and vCPUs (node CPU count). The node's score
    is the *limiting* resource (``min`` of the two ratios); the highest score
    wins. Subtracting ``pending_by_node`` makes back-to-back starts alternate.
    Ties resolve to the lowest node id (deterministic).
    """
    nodes = (numa_topology or {}).get("nodes") or {}
    if len(nodes) < 2:
        return None
    numa_hugepages_free_kb = numa_hugepages_free_kb or {}
    pending_by_node = pending_by_node or {}

    best_node = None
    best_score = None
    for node in sorted(nodes):
        node_cpus = _cpulist_size(nodes[node].get("cpulist", "")) or 1
        free_kb = numa_hugepages_free_kb.get(node, 0)
        pending = pending_by_node.get(node, {})
        pending_ram_kb = pending.get("ram_kb", 0)
        pending_vcpus = pending.get("vcpus", 0)

        mem_headroom = free_kb - pending_ram_kb - domain_memory_kb
        vcpu_headroom = node_cpus - pending_vcpus - domain_vcpus

        mem_ratio = mem_headroom / (free_kb or 1)
        vcpu_ratio = vcpu_headroom / node_cpus
        score = min(mem_ratio, vcpu_ratio)

        if best_score is None or score > best_score:
            best_score = score
            best_node = node
    return best_node
