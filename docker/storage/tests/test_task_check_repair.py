# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the net-new ``task.qemu_img_check_repair`` storage task.

Runs inside the storage image (qemu-img present) over REAL fabricated qcow2s: a
pure leak and a production-shape ``OFLAG_COPIED refcount=0`` corruption. Each case
drives the task body and asserts the disk's post-repair state directly, so the
tests fail on ``origin/main`` (where the task does not exist) and would fail again
if the ``-r`` call, the ``what`` routing or the guards were dropped.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ``storage_lib`` lives beside the worker in the image (/utils) and under
# docker/storage/utils in the repo; ``task`` is the isardvdi_storage package; the
# fabrication helper is this directory's own module.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/opt/isardvdi/isardvdi_task")
sys.path.insert(0, "/utils")

if shutil.which("qemu-img") is None:
    pytest.skip("qemu-img not available", allow_module_level=True)

import _qcow2_fabricate as fab  # noqa: E402
from isardvdi_storage import task  # noqa: E402  the storage worker task module
from storage_lib import qcow  # noqa: E402


def _create_clean(path, size="10M"):
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", str(path), size],
        check=True,
        capture_output=True,
    )


# --- fabrication precondition: the fixtures are what we claim -----------------


def test_fabricated_leak_is_a_pure_leak(tmp_path):
    disk = fab.fabricate_leaky_qcow2(tmp_path / "leak.qcow2")
    report = qcow.qemu_img_check_report(disk)
    assert report["leaks"] >= 1
    assert report["corruptions"] == 0
    # a leak alone never makes a disk unsound
    assert report["ok"] is True


def test_fabricated_corruption_is_a_corruption(tmp_path):
    disk = fab.fabricate_corrupt_qcow2(tmp_path / "corrupt.qcow2")
    report = qcow.qemu_img_check_report(disk)
    assert report["corruptions"] >= 1
    assert report["ok"] is False


# --- the repair task over real files -----------------------------------------


def test_repair_leaks_cleans_a_leaky_disk(tmp_path):
    disk = fab.fabricate_leaky_qcow2(tmp_path / "leak.qcow2")
    assert qcow.qemu_img_check_report(disk)["leaks"] >= 1  # precondition

    result = task.qemu_img_check_repair(disk, "leaks")

    assert result["what"] == "leaks"
    assert result["before"]["leaks"] >= 1
    assert result["after"]["leaks"] == 0
    assert result["ok"] is True
    # and the file itself is now clean, not just the report we returned
    assert qcow.qemu_img_check_report(disk)["ok"] is True


def test_repair_all_cleans_a_repairable_corruption(tmp_path):
    disk = fab.fabricate_corrupt_qcow2(tmp_path / "corrupt.qcow2")
    assert qcow.qemu_img_check_report(disk)["corruptions"] >= 1  # precondition

    result = task.qemu_img_check_repair(disk, "all")

    assert result["what"] == "all"
    assert result["before"]["corruptions"] >= 1
    assert result["after"]["ok"] is True
    assert result["ok"] is True


def test_repair_leaks_cannot_fix_a_corruption_and_says_so(tmp_path):
    """``-r leaks`` on a corrupt disk: the repair runs but leaves the corruption,
    which is a result (row stays damaged with the new reason), NOT a task
    failure. The task must return ok=False, not raise."""
    disk = fab.fabricate_corrupt_qcow2(tmp_path / "corrupt.qcow2")

    result = task.qemu_img_check_repair(disk, "leaks")

    assert result["ok"] is False
    assert result["after"]["corruptions"] >= 1
    # still corrupt on disk, so the row must not be flipped to ready
    assert qcow.qemu_img_check_report(disk)["ok"] is False


def test_repair_is_a_noop_on_a_clean_disk(tmp_path):
    disk = tmp_path / "clean.qcow2"
    _create_clean(disk)
    result = task.qemu_img_check_repair(str(disk), "all")
    assert result["ok"] is True
    assert result["before"]["ok"] is True and result["after"]["ok"] is True


def test_repair_result_has_the_contract_shape(tmp_path):
    disk = fab.fabricate_leaky_qcow2(tmp_path / "leak.qcow2")
    result = task.qemu_img_check_repair(disk, "leaks")
    assert set(result) == {"what", "before", "after", "ok"}
    for side in ("before", "after"):
        assert {"ok", "summary"} <= set(result[side])


# --- guards ------------------------------------------------------------------


def test_repair_rejects_unknown_what(tmp_path):
    disk = fab.fabricate_leaky_qcow2(tmp_path / "leak.qcow2")
    with pytest.raises(ValueError):
        task.qemu_img_check_repair(disk, "everything")


def test_repair_raises_on_missing_file(tmp_path):
    with pytest.raises(RuntimeError):
        task.qemu_img_check_repair(str(tmp_path / "nope.qcow2"), "leaks")


def test_repair_refuses_a_disk_in_use(tmp_path, monkeypatch):
    """The hard guard: a disk a hypervisor holds open is never rewritten. The
    task must refuse BEFORE running qemu-img check -r."""
    disk = fab.fabricate_leaky_qcow2(tmp_path / "leak.qcow2")
    monkeypatch.setattr(
        qcow, "is_file_in_use", lambda path: (True, "test: locked by a hypervisor")
    )
    called = []
    monkeypatch.setattr(task, "_run_cancellable", lambda cmd: called.append(cmd))
    with pytest.raises(RuntimeError):
        task.qemu_img_check_repair(disk, "leaks")
    assert called == []  # never touched the file
    # and the disk is untouched: still leaking, not repaired
    assert qcow.qemu_img_check_report(disk)["leaks"] >= 1
