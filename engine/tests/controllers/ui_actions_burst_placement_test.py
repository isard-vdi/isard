"""A burst of non-GPU starts through the real balancer on a hugepage host."""

import copy
import sys
from unittest.mock import MagicMock

import pytest

_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    import engine.controllers.ui_actions as ui
    import engine.models.balancers as balancers
finally:
    sys.modules.update(_rethinkdb_stubs)

for _name, _value in {"log": None, "logs": None, "LOG_LEVEL": "INFO"}.items():
    if not hasattr(ui, _name):
        setattr(
            ui,
            _name,
            MagicMock(name=f"ui_actions.{_name}") if _value is None else _value,
        )

GIB = 1048576

DOMAIN_XML = (
    "<domain type='kvm'><name>d</name>"
    "<memory unit='KiB'>{kb}</memory><vcpu>2</vcpu>"
    "<os><type arch='x86_64' machine='pc-q35-8.2'>hvm</type></os>"
    "<devices><emulator>/usr/bin/qemu-kvm</emulator>"
    "<disk type='file' device='disk'><driver name='qemu' type='qcow2'/>"
    "<source file='/x.qcow2'/><target dev='vda' bus='virtio'/></disk>"
    "</devices></domain>"
)


def _host(
    hyp_id,
    total_gb=160,
    pool_gb=64,
    pool_free_gb=64,
    available_gb=72,
    guests_gb=64,
    min_free_gb=8,
):
    """160 GiB host: a free 64 GiB pool, 64 GiB of guests only partly touched."""
    total, pool, pool_free = total_gb * GIB, pool_gb * GIB, pool_free_gb * GIB
    available = available_gb * GIB
    return {
        "id": hyp_id,
        "min_free_mem_gb": min_free_gb,
        "hugepages_info": {
            "mounted": True,
            "1G": {"total": pool_gb},
            "mount_sizes": ["1G"],
        },
        "numa_topology": {},
        "stats": {
            "mem_stats": {
                "total": total,
                "available": available,
                "used": total - available - pool_free,
                "hugepages_total_kb": pool,
                "hugepages_free_kb": pool_free,
                "hugepages_used_kb": pool - pool_free,
                "numa_hugepages_free_kb": {},
                "guests_kb": guests_gb * GIB,
            }
        },
    }


def _regular_capacity_kb(host):
    mem = host["stats"]["mem_stats"]
    return mem["total"] - mem["hugepages_total_kb"] - host["min_free_mem_gb"] * GIB


def _committed_regular_kb(host):
    mem = host["stats"]["mem_stats"]
    return mem["guests_kb"] - mem["hugepages_used_kb"]


class _Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def burst(monkeypatch):
    """Run N starts against hosts whose stats only move if ``refresh`` says so."""

    def _run(
        hosts,
        starts,
        memory_gb=8,
        seconds_between=1.0,
        refresh=False,
        balancer_type="available_ram_percent",
    ):
        hosts = {h["id"]: copy.deepcopy(h) for h in hosts}
        clock = _Clock()
        monkeypatch.setattr(balancers.time, "time", clock)
        monkeypatch.setattr(
            balancers,
            "get_hypers_online",
            lambda *a, **k: [copy.deepcopy(h) for h in hosts.values()],
        )
        monkeypatch.setattr(balancers, "get_pools_threads_running", lambda h: h)
        monkeypatch.setattr(
            balancers, "weighted_select", lambda sorted_hypers: sorted_hypers[0]
        )
        monkeypatch.setattr(ui, "get_domain", lambda _id: {"create_dict": {}})
        monkeypatch.setattr(ui, "get_hyp_machine_types", lambda _h: [])
        failed = []
        monkeypatch.setattr(
            ui,
            "update_domain_status",
            lambda status, id_domain, **k: failed.append((id_domain, k.get("detail"))),
        )

        balancer = balancers.BalancerInterface(balancer_type=balancer_type)
        queued = []

        class _Queue:
            def __init__(self, hyp_id):
                self.hyp_id = hyp_id

            def qsize(self):
                return 0

            def put(self, action, priority):
                queued.append((self.hyp_id, action))

        class _Workers(dict):
            def __getitem__(self, key):
                return _Queue(key)

        class _Pool:
            pass

        _Pool.balancer = balancer

        class _Q:
            workers = _Workers()

        class _Manager:
            pools = {"default": _Pool()}
            q = _Q()

        actions = ui.UiActions.__new__(ui.UiActions)
        actions.manager = _Manager()
        xml = DOMAIN_XML.format(kb=int(memory_gb * GIB))
        placed = {h: {"regular": 0, "hugepages": 0} for h in hosts}
        for i in range(starts):
            before = len(queued)
            actions.start_domain_from_xml(
                xml,
                f"desktop-{i}",
                pool_id="default",
                storage_pool_id="pool",
                domain_memory_gb=memory_gb,
            )
            if len(queued) > before:
                hyp_id, action = queued[-1]
                kind = "hugepages" if "<hugepages>" in action["xml"] else "regular"
                placed[hyp_id][kind] += 1
                if refresh:
                    # The worker started it and wrote fresh stats.
                    mem = hosts[hyp_id]["stats"]["mem_stats"]
                    mem["guests_kb"] += int(memory_gb * GIB)
                    if kind == "hugepages":
                        mem["hugepages_used_kb"] += int(memory_gb * GIB)
                        mem["hugepages_free_kb"] -= int(memory_gb * GIB)
                    release = getattr(balancers, "release_pending_start", None)
                    if release is not None:
                        release(hyp_id, f"desktop-{i}")
            clock.now += seconds_between
        return placed, hosts, failed

    return _run


def _regular_after(host, placed, memory_gb=8):
    return _committed_regular_kb(host) + placed["regular"] * memory_gb * GIB


def test_a_burst_on_the_only_host_fills_the_pool_instead_of_overcommitting(burst):
    host = _host("h1")
    placed, _, _ = burst([host], starts=8)

    # 24 GiB of regular memory was left: three desktops fit, five go to the pool.
    assert placed["h1"] == {"regular": 3, "hugepages": 5}
    assert _regular_after(host, placed["h1"]) <= _regular_capacity_kb(host)


def test_a_burst_spread_over_two_hosts_also_counts_its_own_starts(burst):
    hosts = [_host("h1"), _host("h2")]
    placed, _, _ = burst(hosts, starts=16)

    for host in hosts:
        assert _regular_after(host, placed[host["id"]]) <= _regular_capacity_kb(host)
        assert placed[host["id"]]["hugepages"] * 8 <= 64


def test_starts_queued_longer_than_half_a_minute_are_still_counted(burst):
    """A start waits in the host's queue: it is in flight until the worker runs it."""
    host = _host("h1")
    placed, _, _ = burst([host], starts=8, seconds_between=45.0)

    assert _regular_after(host, placed["h1"]) <= _regular_capacity_kb(host)


def test_a_start_the_stats_already_show_is_not_counted_twice(burst):
    host = _host("h1")
    placed, _, _ = burst([host], starts=8, refresh=True)

    assert placed["h1"] == {"regular": 3, "hugepages": 5}


def test_a_host_with_regular_memory_to_spare_keeps_desktops_off_the_pool(burst):
    host = _host("h1", available_gb=90, guests_gb=0)
    placed, _, _ = burst([host], starts=8)

    assert placed["h1"] == {"regular": 8, "hugepages": 0}


def test_the_only_host_out_of_memory_refuses_the_start_instead_of_oom(burst):
    # Pool full, and regular memory measured short: starting there makes the
    # kernel kill a running desktop to make room.
    host = _host("h1", pool_free_gb=0, available_gb=10, guests_gb=150)
    placed, _, failed = burst([host], starts=1)

    assert placed["h1"] == {"regular": 0, "hugepages": 0}
    assert failed and "memory" in (failed[0][1] or "")


def test_a_host_out_of_memory_is_skipped_for_one_with_room(burst):
    full = _host("h1", pool_free_gb=0, available_gb=10, guests_gb=150)
    roomy = _host("h2", total_gb=60, pool_gb=0, pool_free_gb=0, available_gb=50)
    roomy["hugepages_info"] = {}
    placed, _, failed = burst([full, roomy], starts=2, balancer_type="round_robin")

    assert placed["h1"] == {"regular": 0, "hugepages": 0}
    assert sum(placed["h2"].values()) == 2
    assert not failed


def test_a_host_without_a_pool_starts_desktops_as_before(burst):
    host = _host("h1", total_gb=96, pool_gb=0, pool_free_gb=0, available_gb=4)
    host["hugepages_info"] = {}
    placed, _, failed = burst([host], starts=3)

    assert placed["h1"] == {"regular": 3, "hugepages": 0}
    assert not failed
