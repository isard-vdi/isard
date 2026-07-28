# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the net-new ``task.migration_verify_destination`` task.

Runs inside the storage image (qemu-img present). This is the UNCONDITIONAL
pre-release destination gate: the migration saga deletes a disk's source only
after this task proves the destination exists, passes ``qemu-img check`` and
(for a non-root) backs onto the parent's NEW path. Each case drives the task
body over REAL files and asserts raise-vs-0 directly.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ``storage_lib`` lives beside the worker in the image (/utils) and under
# docker/storage/utils in the repo; support both so the suite collects
# either way. ``task`` itself comes from conftest's path insert.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "utils"))
sys.path.insert(0, "/opt/isardvdi/isardvdi_task")
sys.path.insert(0, "/utils")

if shutil.which("qemu-img") is None:
    pytest.skip("qemu-img not available", allow_module_level=True)

import task  # noqa: E402  the storage worker task module
from storage_lib import qcow  # noqa: E402


def _create_qcow(path, size="10M", backing=None):
    cmd = ["qemu-img", "create", "-f", "qcow2"]
    if backing:
        cmd += ["-b", backing, "-F", "qcow2"]
    cmd += [str(path)]
    if not backing:
        cmd += [size]
    subprocess.run(cmd, check=True, capture_output=True)


# (a) destination absent -> raise (never delete a source against a missing dst)
def test_verify_raises_when_destination_absent(tmp_path):
    with pytest.raises(Exception):
        task.migration_verify_destination(str(tmp_path / "nope.qcow2"))


# (b) destination present but a corrupt/truncated qcow2 -> qemu-img check fails
def test_verify_raises_on_corrupt_destination(tmp_path):
    dst = tmp_path / "dst.qcow2"
    _create_qcow(dst)
    # clobber the qcow2 header so it is no longer a valid image
    with open(dst, "r+b") as fh:
        fh.write(b"\x00" * 512)
    assert qcow.qemu_img_check(str(dst)) is False  # precondition
    with pytest.raises(Exception):
        task.migration_verify_destination(str(dst))


# (c) non-root child whose backing STILL points at the OLD parent path -> raise.
# It would pass qemu-img check (old parent still exists pre-release) but break the
# instant the old parent is released, so the backing must be asserted explicitly.
def test_verify_raises_when_backing_points_at_old_parent(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    old_parent = old / "parent.qcow2"
    new_parent = new / "parent.qcow2"
    _create_qcow(old_parent)
    _create_qcow(new_parent)
    child = new / "child.qcow2"
    _create_qcow(child, backing=old_parent)  # NOT repointed
    # sanity: the chain opens clean (old parent still present), so only the
    # explicit backing assertion can catch the wrong target.
    assert qcow.qemu_img_check(str(child)) is True
    with pytest.raises(Exception):
        task.migration_verify_destination(str(child), expect_backing=str(new_parent))


# (d) non-root child correctly repointed to the NEW parent -> returns 0
def test_verify_passes_for_child_repointed_to_new_parent(tmp_path):
    new = tmp_path / "new"
    new.mkdir()
    new_parent = new / "parent.qcow2"
    _create_qcow(new_parent)
    child = new / "child.qcow2"
    _create_qcow(child, backing=new_parent)
    assert qcow.get_backing_file(str(child)) == str(new_parent)  # precondition
    rc = task.migration_verify_destination(str(child), expect_backing=str(new_parent))
    assert rc == 0


# (e) root disk: destination present + valid, no backing expectation -> returns 0
def test_verify_passes_for_valid_root_destination(tmp_path):
    dst = tmp_path / "root.qcow2"
    _create_qcow(dst)
    rc = task.migration_verify_destination(str(dst))  # expect_backing=None
    assert rc == 0
