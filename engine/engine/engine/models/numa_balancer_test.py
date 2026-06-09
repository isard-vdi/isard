import pytest
from engine.models.numa_balancer import (
    _cpulist_size,
    aggregate_pending_by_node,
    select_balanced_numa_node,
)

GiB = 1048576  # KiB

# A real 2-socket GPU hypervisor shape: 48 CPUs/node, near-equal
# free 1 GiB hugepages — node 0 marginally higher, which is exactly what made the
# old max()-based pick land every non-GPU desktop on node 0.
TWO_NODE_TOPO = {
    "libvirt_numa_ok": False,
    "nodes": {
        "0": {"cpulist": "0-47", "hugepages": {"1G": {"free": 378, "total": 378}}},
        "1": {"cpulist": "48-95", "hugepages": {"1G": {"free": 377, "total": 377}}},
    },
}
NUMA_HP_FREE = {"0": 378 * GiB, "1": 377 * GiB}


@pytest.mark.parametrize(
    "cpulist, expected",
    [
        ("0-47", 48),
        ("48-95", 48),
        ("0-47,90-91", 50),
        ("3", 1),
        ("", 0),
        (None, 0),
        ("0-47,bad", 48),
    ],
)
def test_cpulist_size(cpulist, expected):
    assert _cpulist_size(cpulist) == expected


def test_select_single_node_returns_none():
    topo = {"nodes": {"0": {"cpulist": "0-47"}}}
    assert select_balanced_numa_node(topo, {"0": 378 * GiB}, 2 * GiB, 4, {}) is None


def test_select_empty_topology_returns_none():
    assert select_balanced_numa_node({}, {}, 2 * GiB, 4, {}) is None
    assert select_balanced_numa_node(None, None, 2 * GiB, 4, None) is None


def test_select_no_pending_picks_lowest_on_tie():
    # Two near-equal nodes, no in-flight starts: deterministic -> node 0.
    assert select_balanced_numa_node(TWO_NODE_TOPO, NUMA_HP_FREE, 2 * GiB, 4, {}) == "0"


def test_select_vcpu_pending_shifts_to_other_node():
    # node 0 already carries in-flight vCPUs -> the next desktop must pick node 1.
    pending = {"0": {"ram_kb": 2 * GiB, "vcpus": 4}}
    assert (
        select_balanced_numa_node(TWO_NODE_TOPO, NUMA_HP_FREE, 2 * GiB, 4, pending)
        == "1"
    )


def test_spreads_consecutive_non_gpu_starts():
    # The core fix: a burst of identical non-GPU desktops must NOT all pile on one
    # node. Simulate the engine recording each placement (as pending) before the
    # next pick, exactly as balancers.py does under its lock.
    now = 1000.0
    entries = []  # (node, ram_gb, vcpus, ts) — the balancer's _pending_node list
    counts = {"0": 0, "1": 0}
    for _ in range(6):
        pending = aggregate_pending_by_node(entries, now, 30)
        node = select_balanced_numa_node(
            TWO_NODE_TOPO, NUMA_HP_FREE, 2 * GiB, 4, pending
        )
        counts[node] += 1
        entries.append((node, 2.0, 4, now))
    assert counts == {"0": 3, "1": 3}


def test_select_respects_memory_when_one_node_is_full():
    # node 0 has almost no free hugepages -> a hugepage-backed desktop goes node 1
    # even though node 0 has more idle CPUs.
    hp_free = {"0": 1 * GiB, "1": 300 * GiB}
    assert select_balanced_numa_node(TWO_NODE_TOPO, hp_free, 8 * GiB, 4, {}) == "1"


def test_aggregate_pending_sums_and_expires():
    now = 1000.0
    entries = [
        ("0", 2.0, 4, now - 5),
        ("0", 4.0, 2, now - 5),
        ("1", 8.0, 8, now - 5),
        ("0", 99.0, 99, now - 40),  # expired -> ignored
    ]
    agg = aggregate_pending_by_node(entries, now, 30)
    assert agg == {
        "0": {"ram_kb": 6 * GiB, "vcpus": 6},
        "1": {"ram_kb": 8 * GiB, "vcpus": 8},
    }


def test_aggregate_pending_empty():
    assert aggregate_pending_by_node([], 1000.0, 30) == {}
