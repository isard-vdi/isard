# SPDX-License-Identifier: AGPL-3.0-or-later

"""Media (ISOs) are part of a pool migration, not invisible to it."""

import pytest
from isardvdi_common.lib.storage import migration as mig


def _m(mid, path, pool_id="p1", category="c1"):
    return {
        "id": mid,
        "path_downloaded": path,
        "pool_id": pool_id,
        "category": category,
    }


# --------------------------------------------------------------------------- #
# selection — a media belongs to a plan the same way a disk does
# --------------------------------------------------------------------------- #
def test_pool_selection_takes_the_media_of_that_pool():
    rows = [_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso", pool_id="p2")]
    assert [
        r["id"] for r in mig.media_for_selection(rows, kind="pool", src_pool_id="p1")
    ] == ["a"]


def test_category_selection_takes_the_media_of_that_category():
    rows = [_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso", category="c2")]
    got = mig.media_for_selection(rows, kind="category", category_id="c2")
    assert [r["id"] for r in got] == ["b"]


def test_path_selection_takes_the_media_under_the_prefix():
    rows = [_m("a", "/isard/media/x/a.iso"), _m("b", "/isard/media/y/b.iso")]
    got = mig.media_for_selection(rows, kind="path", path_prefix="/isard/media/x")
    assert [r["id"] for r in got] == ["a"]


def test_a_media_with_no_file_is_not_migratable():
    """A row whose download never landed has nothing to move; planning it would
    fail the copy on a path that was never written."""
    rows = [_m("a", None), _m("b", ""), _m("c", "/isard/media/c.iso")]
    assert [
        r["id"] for r in mig.media_for_selection(rows, kind="pool", src_pool_id="p1")
    ] == ["c"]


# --------------------------------------------------------------------------- #
# items — one per media, no chain, and the kind the summary counts
# --------------------------------------------------------------------------- #
def _items(rows, dst="/isard/pool2/media", size=100):
    return mig.build_media_items(
        "mig-1", rows, dst_dir_of=lambda r: dst, size_of=lambda r: size
    )


def test_each_media_is_its_own_tree_and_carries_kind_media():
    items = _items([_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso")])
    assert [it["kind"] for it in items] == ["media", "media"]
    assert [it["tree_id"] for it in items] == ["a", "b"]
    assert all(it["parent_storage_id"] is None for it in items)


def test_the_destination_keeps_the_file_name():
    """The media row is addressed by id everywhere, but the file on disk keeps
    the name the download gave it, so the copy must not rename it."""
    items = _items([_m("a", "/isard/media/sub/alpine-3.24.iso")])
    assert items[0]["src_path"] == "/isard/media/sub/alpine-3.24.iso"
    assert items[0]["dst_path"] == "/isard/pool2/media/alpine-3.24.iso"


def test_a_media_already_at_its_destination_is_in_place():
    items = _items([_m("a", "/isard/pool2/media/a.iso")])
    assert mig.item_in_place(items[0])


# --------------------------------------------------------------------------- #
# the summary the admin reads must stop saying zero
# --------------------------------------------------------------------------- #
def test_summary_counts_media_separately_from_disks():
    items = _items(
        [_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso")], size=7
    )
    s = mig.summarize_plan(items)
    assert s["media"] == 2
    assert s["desktops"] == 0 and s["derivative_templates"] == 0
    assert s["items_total"] == 2
    assert s["bytes_total"] == 14


def test_item_kinds_media_selects_only_media():
    """The form has offered a media checkbox since the kinds were added; asking
    for media alone must produce the media, not an empty plan."""
    items = _items([_m("a", "/isard/media/a.iso")])
    kept = [it for it in items if mig.kind_selected(it["kind"], ["media"])]
    assert len(kept) == 1
    assert not [it for it in items if mig.kind_selected(it["kind"], ["desktop"])]


# --------------------------------------------------------------------------- #
# residency — a pool holding only ISOs is not empty
# --------------------------------------------------------------------------- #
def test_a_pool_holding_only_media_is_not_drained():
    """`drained` gates the pool delete. Counting only the storage table let a
    pool that still holds ISOs report zero disks and pass that gate."""
    assert mig.pool_is_drained(categories=0, disks=0, media=0, queued=0) is True
    assert mig.pool_is_drained(categories=0, disks=0, media=3, queued=0) is False


@pytest.mark.parametrize(
    "cats,disks,media,queued", [(1, 0, 0, 0), (0, 2, 0, 0), (0, 0, 0, 5)]
)
def test_the_other_drain_conditions_still_hold(cats, disks, media, queued):
    assert mig.pool_is_drained(cats, disks, media, queued) is False


# --------------------------------------------------------------------------- #
# size — the plan cannot reach the pool mounts, but the download measured it
# --------------------------------------------------------------------------- #
def test_media_size_comes_from_what_the_download_recorded():
    assert mig.media_size_bytes({"progress": {"total_bytes": 369098752}}) == 369098752


def test_media_size_is_zero_when_nothing_recorded_it():
    for row in (
        {},
        {"progress": None},
        {"progress": {}},
        {"progress": {"total_bytes": None}},
    ):
        assert mig.media_size_bytes(row) == 0


def test_a_sized_media_counts_towards_the_byte_budget():
    """Zero-byte media would slip past max_bytes_per_occurrence, so a 369 MB ISO
    could start outside a budget that exists to bound the copy."""
    rows = [_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso")]
    rows[0]["progress"] = {"total_bytes": 100}
    rows[1]["progress"] = {"total_bytes": 20}
    items = mig.build_media_items(
        "m", rows, dst_dir_of=lambda r: "/d", size_of=mig.media_size_bytes
    )
    assert mig.summarize_plan(items)["bytes_total"] == 120


def test_tree_ids_selects_named_media_whatever_the_kind():
    """A media is its own tree, so naming it in tree_ids must select it — the
    same escape hatch a disk tree has."""
    rows = [_m("a", "/isard/media/a.iso"), _m("b", "/isard/media/b.iso", pool_id="p2")]
    got = mig.media_for_selection(rows, kind="pool", src_pool_id="p1", tree_ids=["b"])
    assert [r["id"] for r in got] == ["b"]
