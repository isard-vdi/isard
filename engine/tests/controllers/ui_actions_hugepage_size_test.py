"""Which hugepage size the start path asks for."""

import sys

import pytest

_rethinkdb_stubs = {
    name: sys.modules.pop(name)
    for name in list(sys.modules)
    if name == "rethinkdb" or name.startswith("rethinkdb.")
}
try:
    from engine.controllers.ui_actions import pick_hugepage_size
finally:
    sys.modules.update(_rethinkdb_stubs)

GIB = 1048576
BOTH = {"mounted": True, "1G": {"total": 8}, "2M": {"total": 4096}}
BOTH_FREE = 8 * GIB + 4096 * 2048


@pytest.mark.parametrize(
    "memory_kb, expected",
    [
        (4 * GIB, ("1", "G")),
        (GIB, ("1", "G")),
        (512 * 1024, ("2", "M")),
        (1536 * 1024, ("2", "M")),
        (512 * 1024 + 4, None),
        (1000000, None),
    ],
)
def test_the_page_size_divides_the_memory(memory_kb, expected):
    assert pick_hugepage_size(memory_kb, BOTH, BOTH_FREE) == expected


def test_memory_derived_from_fractional_gib():
    assert pick_hugepage_size(0.5 * GIB, BOTH, BOTH_FREE) == ("2", "M")


def test_a_1g_only_pool_gives_half_a_gib_nothing():
    pool = {"mounted": True, "1G": {"total": 8}}
    assert pick_hugepage_size(512 * 1024, pool, 8 * GIB) is None


def test_a_2m_only_pool_serves_whole_gibs():
    pool = {"mounted": True, "2M": {"total": 4096}}
    assert pick_hugepage_size(4 * GIB, pool, 4096 * 2048) == ("2", "M")


def test_free_2m_pages_do_not_count_as_free_1g_pages():
    pool = {"mounted": True, "1G": {"total": 4}, "2M": {"total": 4096}}
    assert pick_hugepage_size(4 * GIB, pool, 4096 * 2048) == ("2", "M")


def test_a_summed_free_figure_that_could_be_either_size_is_not_trusted():
    assert pick_hugepage_size(4 * GIB, BOTH, 8 * GIB) is None


def test_free_1g_pages_do_not_count_as_free_2m_pages():
    assert pick_hugepage_size(512 * 1024, BOTH, 8 * GIB) is None


def test_not_enough_free_pages_of_any_size():
    assert pick_hugepage_size(4 * GIB, BOTH, 2 * GIB) is None


def test_no_pool_at_all():
    assert pick_hugepage_size(4 * GIB, {"mounted": True}, 0) is None


@pytest.mark.parametrize(
    "memory_kb, expected",
    [(512 * 1024, None), (GIB, ("1", "G")), (2 * GIB, ("1", "G"))],
)
def test_a_mixed_pool_mounted_at_1g_never_asks_for_2m(memory_kb, expected):
    pool = dict(BOTH, mount_sizes=["1G"])
    assert pick_hugepage_size(memory_kb, pool, BOTH_FREE) == expected


@pytest.mark.parametrize(
    "memory_kb, expected",
    [(512 * 1024, None), (GIB, ("1", "G")), (2 * GIB, ("1", "G"))],
)
def test_a_1g_only_pool_mounted_at_1g_keeps_its_behaviour(memory_kb, expected):
    pool = {"mounted": True, "1G": {"total": 8}, "mount_sizes": ["1G"]}
    assert pick_hugepage_size(memory_kb, pool, 8 * GIB) == expected


def test_a_mixed_pool_mounted_at_2m_backs_whole_gibs_with_2m():
    pool = dict(BOTH, mount_sizes=["2M"])
    assert pick_hugepage_size(4 * GIB, pool, BOTH_FREE) == ("2", "M")


def test_a_hugepages_dir_that_is_not_hugetlbfs_backs_nothing():
    pool = dict(BOTH, mount_sizes=[])
    assert pick_hugepage_size(GIB, pool, BOTH_FREE) is None
