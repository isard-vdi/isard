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
# either way. ``task`` is imported from the isardvdi_storage package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))
sys.path.insert(0, "/opt/isardvdi/isardvdi_task")
sys.path.insert(0, "/utils")

if shutil.which("qemu-img") is None:
    pytest.skip("qemu-img not available", allow_module_level=True)

from isardvdi_storage import task  # noqa: E402  the storage worker task module
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
    report = task.migration_verify_destination(
        str(child), expect_backing=str(new_parent)
    )
    assert report["leaks"] == 0


# (e) root disk: destination present + valid, no backing expectation -> passes,
# and the report says so with no leaks
def test_verify_passes_for_valid_root_destination(tmp_path):
    dst = tmp_path / "root.qcow2"
    _create_qcow(dst)
    report = task.migration_verify_destination(str(dst))  # expect_backing=None
    assert report == {"leaks": 0, "summary": "no errors"}


# (f) the destination fails AND the source fails the same way: the copy is
# faithful and the SOURCE is damaged. The gate must say so, because a damaged
# source is not a copy error to retry but a disk to mark.
def test_verify_names_a_damaged_source(tmp_path):
    src = tmp_path / "src.qcow2"
    _create_qcow(src)
    with open(src, "r+b") as fh:
        fh.write(b"\x00" * 512)
    dst = tmp_path / "dst.qcow2"
    shutil.copyfile(src, dst)
    with pytest.raises(Exception) as exc:
        task.migration_verify_destination(str(dst), src_path=str(src))
    assert str(exc.value).startswith(task.DAMAGED_SOURCE_MARK)
    assert str(src) in str(exc.value)


# (g) the destination fails but the source is sound: a bad copy, said as such.
def test_verify_blames_the_copy_when_the_source_is_sound(tmp_path):
    src = tmp_path / "src.qcow2"
    _create_qcow(src)
    dst = tmp_path / "dst.qcow2"
    _create_qcow(dst)
    with open(dst, "r+b") as fh:
        fh.write(b"\x00" * 512)
    with pytest.raises(Exception) as exc:
        task.migration_verify_destination(str(dst), src_path=str(src))
    assert not str(exc.value).startswith(task.DAMAGED_SOURCE_MARK)
    assert "destination" in str(exc.value)


def test_check_report_counts_what_qemu_img_says(tmp_path):
    good = tmp_path / "good.qcow2"
    _create_qcow(good)
    report = qcow.qemu_img_check_report(str(good))
    assert report["ok"] is True and report["summary"] == "no errors"
    with open(good, "r+b") as fh:
        fh.write(b"\x00" * 512)
    report = qcow.qemu_img_check_report(str(good))
    assert report["ok"] is False
    assert report["summary"]


# (h) leaked clusters waste space and harm no data: they must never fail the
# gate, and never turn a sound disk into a damaged one. qemu-img cannot be made
# to leak on demand, so the report is fed the JSON qemu-img prints for one.
def test_check_report_lets_leaks_through_and_names_them(monkeypatch):
    class _R:
        returncode = 3  # what qemu-img exits with for leaks only
        stdout = '{"corruptions": 0, "leaks": 593, "check-errors": 0}'
        stderr = ""

    monkeypatch.setattr(qcow.subprocess, "run", lambda *a, **k: _R())
    report = qcow.qemu_img_check_report("/any.qcow2")
    assert report["ok"] is True
    assert report["leaks"] == 593 and report["summary"] == "leaks=593"


def test_check_report_fails_on_corruptions(monkeypatch):
    class _R:
        returncode = 2
        stdout = '{"corruptions": 62, "leaks": 0, "check-errors": 0}'
        stderr = ""

    monkeypatch.setattr(qcow.subprocess, "run", lambda *a, **k: _R())
    report = qcow.qemu_img_check_report("/any.qcow2")
    assert report["ok"] is False and report["summary"] == "corruptions=62"


def test_verify_passes_a_destination_with_leaks_only(tmp_path, monkeypatch):
    """The field case: a 419-disk migration blocked at 64 % on a healthy disk
    with 593 leaked clusters, identical on source and copy."""
    dst = tmp_path / "dst.qcow2"
    _create_qcow(dst)
    monkeypatch.setattr(
        qcow,
        "qemu_img_check_report",
        lambda path: {
            "ok": True,
            "summary": "leaks=593",
            "leaks": 593,
            "corruptions": 0,
            "check-errors": 0,
        },
    )
    report = task.migration_verify_destination(str(dst), src_path=str(dst))
    assert report["leaks"] == 593  # the mark the runner leaves on the disk
