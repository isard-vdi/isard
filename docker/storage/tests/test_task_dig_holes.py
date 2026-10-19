# SPDX-License-Identifier: AGPL-3.0-or-later

"""``task.dig_holes``: gives back the zero blocks of a file and never changes what it reads."""

import json
import os
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from isardvdi_storage import task

MIB = 1 << 20


def _fallocate_digs_holes():
    try:
        out = subprocess.run(
            ["fallocate", "--help"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return False
    return "dig-holes" in (out.stdout + out.stderr)


@contextmanager
def _nullcontext(*_a, **_k):
    yield


def _qcow(in_use=False, lock_err=None):
    return SimpleNamespace(is_file_in_use=lambda path: (in_use, lock_err))


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(task, "task_heartbeat", _nullcontext)
    monkeypatch.setattr(task, "_storage_qcow", _qcow)
    return task


def _inflated(path):
    with open(path, "wb") as f:
        f.write(b"\xab" * MIB)
        f.write(b"\0" * (16 * MIB))
        f.write(b"\xcd" * MIB)
        f.flush()
        os.fsync(f.fileno())
    return path


def test_the_command_is_fallocate_dig_holes(worker, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    disk = _inflated(tmp_path / "d.qcow2")
    result = worker.dig_holes(str(disk))
    assert calls == [["fallocate", "--dig-holes", str(disk)]]
    assert result["verified"] is False
    assert worker.dig_holes(str(disk), verify=True)["verified"] is True


def test_a_file_that_reads_differently_fails_the_task(worker, monkeypatch, tmp_path):
    disk = _inflated(tmp_path / "d.qcow2")

    def corrupt(cmd):
        with open(disk, "r+b") as f:
            f.write(b"\0")
        return 0

    monkeypatch.setattr(worker, "_run_cancellable", corrupt)
    with pytest.raises(RuntimeError, match="reads differently"):
        worker.dig_holes(str(disk), verify=True)


def test_without_verify_the_file_is_not_read(worker, monkeypatch, tmp_path):
    disk = _inflated(tmp_path / "d.qcow2")
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: 0)
    monkeypatch.setattr(worker, "_sha256", lambda path: pytest.fail("hashed"))
    worker.dig_holes(str(disk))


def test_a_missing_file_fails_the_task(worker, tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        worker.dig_holes(str(tmp_path / "gone.qcow2"))


def test_a_file_a_guest_holds_open_is_not_dug(worker, monkeypatch, tmp_path):
    """Re-checked when the task runs: the file's own lock, not the row, decides."""
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    monkeypatch.setattr(
        worker, "_storage_qcow", lambda: _qcow(True, 'Failed to get "write" lock')
    )
    disk = _inflated(tmp_path / "d.qcow2")
    with pytest.raises(RuntimeError, match="in use by a hypervisor"):
        worker.dig_holes(str(disk))
    assert calls == []


@pytest.mark.skipif(
    not _fallocate_digs_holes(), reason="this fallocate has no --dig-holes"
)
def test_it_gives_the_zeros_back_and_reads_the_same(worker, tmp_path):
    disk = _inflated(tmp_path / "d.qcow2")
    before = open(disk, "rb").read()
    result = worker.dig_holes(str(disk))
    assert result["reclaimed"] >= 8 * MIB
    assert result["after"] == os.stat(disk).st_blocks * 512
    assert open(disk, "rb").read() == before


class _Done:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.returncode = stdout, returncode


def test_reclaimable_counts_only_the_top_layer_data(monkeypatch):
    extents = (
        '[{"start": 0, "length": 1048576, "depth": 0, "data": true},'
        ' {"start": 1048576, "length": 4194304, "depth": 1, "data": true},'
        ' {"start": 5242880, "length": 8388608, "depth": 0, "data": false}]'
    )
    monkeypatch.setattr(task, "run", lambda *a, **k: _Done(extents))
    assert task._reclaimable_zeros("/x.qcow2", 9 * MIB) == 8 * MIB


def test_preallocated_zero_clusters_are_not_data(monkeypatch):
    extents = (
        '[{"start": 0, "length": 1048576, "depth": 0, "zero": false, "data": true},'
        ' {"start": 1048576, "length": 8388608, "depth": 0, "zero": true, "data": true}]'
    )
    monkeypatch.setattr(task, "run", lambda *a, **k: _Done(extents))
    assert task._reclaimable_zeros("/x.qcow2", 9 * MIB) == 8 * MIB


def test_reclaimable_is_unknown_when_map_fails(monkeypatch):
    monkeypatch.setattr(task, "run", lambda *a, **k: _Done("", returncode=1))
    assert task._reclaimable_zeros("/x.qcow2", 9 * MIB) is None


@pytest.mark.skipif(
    subprocess.run(
        ["sh", "-c", "command -v qemu-img && command -v qemu-io"], capture_output=True
    ).returncode,
    reason="qemu-img/qemu-io not available",
)
def test_reclaimable_sees_an_inflated_copy(tmp_path):
    """With extended_l2 a preallocated subcluster is a zero in the qcow2 itself, so inflation shows."""
    sparse = tmp_path / "s.qcow2"
    subprocess.run(
        [
            "qemu-img",
            "create",
            "-q",
            "-f",
            "qcow2",
            "-o",
            "cluster_size=2M,extended_l2=on,preallocation=metadata",
            str(sparse),
            "64M",
        ],
        check=True,
    )
    subprocess.run(
        ["qemu-io", "-f", "qcow2", "-c", "write -P 0xab 0 1M", str(sparse)],
        check=True,
        capture_output=True,
    )
    extents = json.loads(
        subprocess.run(
            ["qemu-img", "map", "--output=json", str(sparse)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    if any(e.get("data") and e["length"] > 8 * MIB for e in extents):
        pytest.skip("this qemu-img does not mark preallocated subclusters as zero")
    inflated = tmp_path / "i.qcow2"
    inflated.write_bytes(sparse.read_bytes())
    for path, low, high in ((sparse, 0, 16 * MIB), (inflated, 48 * MIB, 80 * MIB)):
        actual = os.stat(path).st_blocks * 512
        assert low <= task._reclaimable_zeros(str(path), actual) <= high
