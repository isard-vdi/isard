# SPDX-License-Identifier: AGPL-3.0-or-later
"""cleanup must never propose deleting a file a live disk reads through, or is."""

import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from storage_lib.consistency import (  # noqa: E402
    deletable_after_live_guard,
    uuids_needed_by_live,
)

POOL = "/isard/storage_pools/default"


def df(path, uuid, backing_uuid=None, backing_raw=None, size=100):
    return {
        "path": path,
        "uuid": uuid,
        "backing_uuid": backing_uuid,
        "backing_raw": backing_raw,
        "size": size,
        "readable": True,
    }


def test_guard_excludes_deleted_template_that_backs_a_live_child_with_stale_pointer():
    # move_disks moved the template aside; the live child still records the OLD
    # backing path, so cleanup's path-keyed reverse_map never links them and the
    # template lands in the deletable set. The uuid-resolved guard catches it.
    parent = f"{POOL}/templates/moved/tpl.qcow2"
    files = [
        df(parent, "tpl"),
        df(f"{POOL}/desktops/live.qcow2", "live", "tpl", f"{POOL}/templates/tpl.qcow2"),
        df(f"{POOL}/desktops/orphan.qcow2", "orphan"),
    ]
    raw_deletable = {parent, f"{POOL}/desktops/orphan.qcow2"}
    # control: without the guard, cleanup would delete the sustaining template
    assert parent in raw_deletable

    kept, protected = deletable_after_live_guard(raw_deletable, files, {"live"})
    assert parent in protected
    assert parent not in kept
    # a genuinely rowless, unbacked orphan is still deletable
    assert f"{POOL}/desktops/orphan.qcow2" in kept


def test_guard_protects_a_live_disk_that_is_merely_mislocated():
    # a ready desktop whose file sits at the wrong pool reads as an orphan to
    # cleanup; deleting it would kill a working desktop. The guard keeps it.
    mislocated = f"{POOL}/templates/r3.qcow2"
    files = [df(mislocated, "r3")]
    kept, protected = deletable_after_live_guard({mislocated}, files, {"r3"})
    assert protected == {mislocated}
    assert kept == set()


def test_guard_is_a_no_op_without_live_disks():
    files = [df(f"{POOL}/templates/x.qcow2", "x")]
    kept, protected = deletable_after_live_guard(
        {f"{POOL}/templates/x.qcow2"}, files, set()
    )
    assert protected == set()
    assert kept == {f"{POOL}/templates/x.qcow2"}


def test_needed_by_live_is_the_union_of_live_and_their_backing():
    files = [
        df(f"{POOL}/templates/tpl.qcow2", "tpl"),
        df(f"{POOL}/desktops/live.qcow2", "live", "tpl", f"{POOL}/templates/tpl.qcow2"),
    ]
    assert uuids_needed_by_live(files, {"live"}) == {"live", "tpl"}
