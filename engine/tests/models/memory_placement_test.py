"""Which memory a non-GPU desktop gets on a host with a hugepage pool."""

import pytest

from engine.models.memory_placement import (
    HUGEPAGES,
    REGULAR,
    committed_regular_kb,
    plan_memory_backing,
    regular_room_kb,
)

GIB = 1048576
POOL = {"mounted": True, "1G": {"total": 64}, "mount_sizes": ["1G"]}


def _mem(total_gb=160, pool_gb=64, pool_free_gb=64, available_gb=72, guests_gb=64):
    return {
        "total": total_gb * GIB,
        "available": available_gb * GIB,
        "hugepages_total_kb": pool_gb * GIB,
        "hugepages_free_kb": pool_free_gb * GIB,
        "hugepages_used_kb": (pool_gb - pool_free_gb) * GIB,
        "guests_kb": guests_gb * GIB,
    }


def test_guests_in_hugepages_do_not_commit_regular_memory():
    assert committed_regular_kb(_mem(pool_free_gb=48, guests_gb=64)) == 48 * GIB


def test_unknown_guests_memory_is_none_not_zero():
    mem = _mem()
    del mem["guests_kb"]
    assert committed_regular_kb(mem) is None
    assert regular_room_kb(mem, 8 * GIB) == (64 * GIB, None)


def test_room_is_counted_against_committed_and_measured_memory():
    # 96 GiB regular, 8 reserved, 64 committed: 24 left, though 64 measured.
    assert regular_room_kb(_mem(), 8 * GIB) == (64 * GIB, 24 * GIB)


def test_committed_regular_memory_sends_the_desktop_to_the_pool():
    # Measured memory looks plenty (the guests have not touched theirs yet).
    plan = plan_memory_backing(_mem(), POOL, 8, 8 * GIB, pending_regular_kb=24 * GIB)
    assert plan == HUGEPAGES


def test_regular_memory_with_room_keeps_the_desktop_off_the_pool():
    assert plan_memory_backing(_mem(), POOL, 8, 8 * GIB) == REGULAR


def test_measured_shortage_alone_still_uses_the_pool():
    mem = _mem(available_gb=10, guests_gb=0)
    assert plan_memory_backing(mem, POOL, 8, 8 * GIB) == HUGEPAGES


def test_pool_pages_already_promised_to_starts_in_flight_are_not_free():
    mem = _mem(pool_free_gb=8)
    plan = plan_memory_backing(
        mem, POOL, 8, 8 * GIB, pending_regular_kb=24 * GIB, pending_hugepages_kb=8 * GIB
    )
    # Pool spoken for and regular committed, but measured memory has room: it
    # starts over committed, as a host without a pool does.
    assert plan == REGULAR


def test_no_room_anywhere_is_none():
    mem = _mem(pool_free_gb=0, available_gb=10, guests_gb=150)
    assert plan_memory_backing(mem, POOL, 8, 8 * GIB) is None


def test_a_host_without_a_pool_is_never_refused():
    mem = _mem(pool_gb=0, pool_free_gb=0, available_gb=0)
    assert plan_memory_backing(mem, {}, 8, 8 * GIB) == REGULAR
    assert plan_memory_backing(mem, {"mounted": False}, 8, 8 * GIB) == REGULAR


@pytest.mark.parametrize("memory_kb", [512 * 1024, 1536 * 1024])
def test_a_size_the_pool_pages_cannot_divide_stays_regular_if_measured_fits(
    memory_kb,
):
    # 1 GiB pages cannot back half a GiB: regular is the only option.
    plan = plan_memory_backing(_mem(), POOL, 8, memory_kb, pending_regular_kb=24 * GIB)
    assert plan == REGULAR


def test_a_host_with_no_stats_yet_is_not_refused():
    assert plan_memory_backing({}, POOL, 0, GIB) == REGULAR
    assert plan_memory_backing(None, POOL, 0, GIB) == REGULAR
