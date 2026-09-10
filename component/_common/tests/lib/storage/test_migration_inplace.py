# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the origin==destination (all-in-place) rejection helper.

A path/category selection whose destination pool is the one the disks already
live in resolves every disk in-place (dst == src) — nothing would move, and the
release would move_delete the live source. The service rejects such a job; a
PARTIAL in-place set (some disks already in dst, others not) stays legal.
"""

from isardvdi_common.lib.storage import migration as mig


def _it(src, dst):
    return {"src_path": src, "dst_path": dst}


def test_empty_plan_is_not_all_in_place():
    assert mig.all_in_place([]) is False


def test_all_in_place_true_when_every_disk_dst_equals_src():
    items = [_it("/a/1.qcow2", "/a/1.qcow2"), _it("/a/2.qcow2", "/a/2.qcow2")]
    assert mig.all_in_place(items) is True


def test_partial_in_place_is_allowed():
    items = [_it("/a/1.qcow2", "/a/1.qcow2"), _it("/a/2.qcow2", "/b/2.qcow2")]
    assert mig.all_in_place(items) is False


def test_none_moving_is_not_in_place():
    # a disk with no dst yet is not "in place" (it will move once resolved)
    assert mig.all_in_place([_it("/a/1.qcow2", None)]) is False
