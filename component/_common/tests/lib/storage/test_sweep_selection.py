# SPDX-License-Identifier: AGPL-3.0-or-later

"""The sweep picks disks oldest-first, skips the live ones, and honours the budget."""

from isardvdi_common.lib.storage.sweep import select_within_budget


def _c(id, size_bytes=0, started=False, has_children=False):
    return {
        "id": id,
        "size_bytes": size_bytes,
        "started": started,
        "has_children": has_children,
    }


def test_no_caps_takes_every_idle_candidate():
    out = select_within_budget([_c("a"), _c("b"), _c("c")])
    assert out["selected"] == ["a", "b", "c"]
    assert out["skipped_started"] == [] and out["skipped_budget"] == []


def test_a_started_desktops_disk_is_skipped():
    out = select_within_budget([_c("a", started=True), _c("b")])
    assert out["selected"] == ["b"]
    assert out["skipped_started"] == ["a"]


def test_disk_cap_stops_after_max_disks():
    out = select_within_budget([_c("a"), _c("b"), _c("c")], max_disks=1)
    assert out["selected"] == ["a"]
    assert out["skipped_budget"] == ["b", "c"]


def test_byte_budget_enqueues_one_and_leaves_the_rest():
    out = select_within_budget([_c("a", 10), _c("b", 10), _c("c", 10)], max_bytes=10)
    assert out["selected"] == ["a"]
    assert out["skipped_budget"] == ["b", "c"]
    assert out["used_bytes"] == 10


def test_a_disk_cap_of_zero_selects_nothing():
    out = select_within_budget([_c("a"), _c("b")], max_disks=0)
    assert out["selected"] == []
    assert out["skipped_budget"] == ["a", "b"]


def test_a_disk_with_descendants_is_excluded_and_counted():
    """The red line: a write action never selects a disk that has children."""
    out = select_within_budget([_c("a", has_children=True), _c("b")])
    assert out["selected"] == ["b"]
    assert out["skipped_has_descendants"] == ["a"]
    assert out["skipped_started"] == [] and out["skipped_budget"] == []


def test_a_disk_with_descendants_never_spends_the_budget():
    """Exclusion takes precedence over the caps: a parent is dropped for free, so
    the disk cap still admits a full quota of leaves and the parent is reported."""
    out = select_within_budget(
        [_c("p", has_children=True), _c("a"), _c("b")], max_disks=1
    )
    assert out["selected"] == ["a"]
    assert out["skipped_has_descendants"] == ["p"]
    assert out["skipped_budget"] == ["b"]
