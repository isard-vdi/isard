# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the migration quiesce / autostart-guard pure helpers."""

from isardvdi_common.lib.storage import migration as mig


# --------------------------------------------------------------------------- #
# quiesce_decision
# --------------------------------------------------------------------------- #
def test_quiesce_stopped_is_ok():
    assert mig.quiesce_decision("Stopped", force_stop=False) == "ok"
    assert mig.quiesce_decision("Stopped", force_stop=True) == "ok"
    assert mig.quiesce_decision("Failed", force_stop=False) == "ok"
    assert mig.quiesce_decision(None, force_stop=False) == "ok"  # template / no domain


def test_quiesce_running_without_forcestop_skips():
    assert mig.quiesce_decision("Started", force_stop=False) == "skip"
    assert mig.quiesce_decision("Shutting-down", force_stop=False) == "skip"


def test_quiesce_running_with_forcestop_stops():
    assert mig.quiesce_decision("Started", force_stop=True) == "force_stop"
    assert mig.quiesce_decision("Shutting-down", force_stop=True) == "force_stop"


# --------------------------------------------------------------------------- #
# descendant_item_ids (subtree skip cascade)
# --------------------------------------------------------------------------- #
def _items():
    return [
        {"id": "i0", "storage_id": "root", "parent_storage_id": None},
        {"id": "i1", "storage_id": "a", "parent_storage_id": "root"},
        {"id": "i2", "storage_id": "b", "parent_storage_id": "root"},
        {"id": "i3", "storage_id": "a1", "parent_storage_id": "a"},
        {"id": "i4", "storage_id": "a1x", "parent_storage_id": "a1"},
    ]


def test_descendants_excludes_self_by_default():
    ids = mig.descendant_item_ids(_items(), "a")
    assert ids == {"i3", "i4"}  # a1 and a1x; not 'a' itself, not siblings


def test_descendants_include_self():
    ids = mig.descendant_item_ids(_items(), "a", include_self=True)
    assert ids == {"i1", "i3", "i4"}


def test_descendants_of_root_is_whole_tree():
    ids = mig.descendant_item_ids(_items(), "root")
    assert ids == {"i1", "i2", "i3", "i4"}


def test_descendants_of_leaf_is_empty():
    assert mig.descendant_item_ids(_items(), "a1x") == set()
