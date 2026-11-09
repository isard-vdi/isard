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


@contextmanager
def _qemu_holds(path, *bytes_):
    """Another open file description holding QEMU's lock bytes, as a guest would."""
    from isardvdi_common.lib.storage import qemu_locks

    fd = os.open(path, os.O_RDONLY)
    try:
        for byte in bytes_:
            qemu_locks._flock(
                fd, qemu_locks.F_OFD_SETLK, qemu_locks.fcntl.F_RDLCK, byte
            )
        yield fd
    finally:
        os.close(fd)


@pytest.mark.parametrize("byte", [101, 103], ids=["write", "resize"])
def test_a_file_a_writer_holds_open_is_not_dug(worker, monkeypatch, tmp_path, byte):
    """Re-checked when the task runs: the file's own lock, not the row, decides."""
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    disk = _inflated(tmp_path / "d.qcow2")
    with _qemu_holds(disk, 100, byte):
        with pytest.raises(RuntimeError, match="dig_holes refused"):
            worker.dig_holes(str(disk))
    assert calls == []


def test_a_base_its_running_descendants_read_is_dug(worker, monkeypatch, tmp_path):
    """A descendant's QEMU reads its base and refuses to share write: no writer."""
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    disk = _inflated(tmp_path / "d.qcow2")
    with _qemu_holds(disk, 100, 201, 203):
        worker.dig_holes(str(disk), verify=True)
    assert calls == [["fallocate", "--dig-holes", str(disk)]]


def test_no_writer_can_open_the_file_while_it_is_dug(worker, monkeypatch, tmp_path):
    from isardvdi_common.lib.storage import qemu_locks

    disk = _inflated(tmp_path / "d.qcow2")
    seen = []

    def punch(cmd):
        probe = os.open(disk, os.O_RDONLY)
        try:
            seen.append([qemu_locks.held_by_others(probe, b) for b in (201, 203, 101)])
        finally:
            os.close(probe)
        return 0

    monkeypatch.setattr(worker, "_run_cancellable", punch)
    worker.dig_holes(str(disk), verify=True)
    assert seen == [[True, True, False]]
    probe = os.open(disk, os.O_RDONLY)
    try:
        assert not qemu_locks.held_by_others(probe, 201), "the dig kept its lock"
    finally:
        os.close(probe)


def _have(*tools):
    from shutil import which

    return all(which(t) for t in tools)


@pytest.mark.skipif(not _have("qemu-img", "qemu-io"), reason="no qemu-img/qemu-io")
def test_qemu_cannot_open_a_base_for_writing_while_it_is_dug(
    worker, monkeypatch, tmp_path
):
    disk = str(tmp_path / "base.qcow2")
    subprocess.run(["qemu-img", "create", "-f", "qcow2", disk, "64M"], check=True)
    seen = {}

    def punch(cmd):
        write = subprocess.run(
            ["qemu-io", "-c", "write 0 4k", disk], capture_output=True, text=True
        )
        read = subprocess.run(
            ["qemu-io", "-r", "-c", "read 0 4k", disk], capture_output=True, text=True
        )
        seen.update(write=write, read=read)
        return 0

    monkeypatch.setattr(worker, "_run_cancellable", punch)
    worker.dig_holes(disk, verify=True)
    assert seen["write"].returncode != 0
    assert "lock" in (seen["write"].stderr + seen["write"].stdout).lower()
    assert seen["read"].returncode == 0, seen["read"].stderr
    after = subprocess.run(
        ["qemu-io", "-c", "write 0 4k", disk], capture_output=True, text=True
    )
    assert after.returncode == 0, after.stderr


@contextmanager
def _qemu_io_open(disk, *flags):
    """A qemu-io that keeps ``disk`` open (and locked) until it is closed."""
    import time

    proc = subprocess.Popen(
        ["qemu-io", *flags, disk],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        proc.stdin.write("read 0 512\n")
        proc.stdin.flush()
        time.sleep(1)
        assert proc.poll() is None, proc.stdout.read()
        yield proc
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


@pytest.mark.skipif(not _have("qemu-img", "qemu-io"), reason="no qemu-img/qemu-io")
def test_a_disk_qemu_holds_for_writing_is_not_dug(worker, monkeypatch, tmp_path):
    disk = str(tmp_path / "leaf.qcow2")
    subprocess.run(["qemu-img", "create", "-f", "qcow2", disk, "64M"], check=True)
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    with _qemu_io_open(disk):
        with pytest.raises(RuntimeError, match="write"):
            worker.dig_holes(disk)
    assert calls == []


@pytest.mark.skipif(not _have("qemu-img", "qemu-io"), reason="no qemu-img/qemu-io")
def test_a_base_a_descendant_reads_through_is_dug(worker, monkeypatch, tmp_path):
    base = str(tmp_path / "base.qcow2")
    child = str(tmp_path / "child.qcow2")
    subprocess.run(["qemu-img", "create", "-f", "qcow2", base, "64M"], check=True)
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", base, child],
        check=True,
    )
    calls = []
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: calls.append(cmd) or 0)
    with _qemu_io_open(child):
        worker.dig_holes(base, verify=True)
    assert calls == [["fallocate", "--dig-holes", base]]


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


def test_a_measure_no_longer_estimates_the_zeros(monkeypatch):
    info = json.dumps([{"actual-size": 9 * MIB, "format": "qcow2"}])
    commands = []
    monkeypatch.setattr(
        task, "run", lambda cmd, *a, **k: commands.append(cmd) or _Done(info)
    )
    out = task.qemu_img_info_backing_chain("s1", "/x.qcow2")
    assert "reclaimable-zeros" not in out
    assert not any("map" in cmd for cmd in commands)


class _Job:
    def __init__(self, log):
        self.meta, self.log = {}, log

    def save_meta(self):
        self.log.append(("meta", dict(self.meta)))


def test_the_job_says_it_began_punching_before_the_file_is_written(
    worker, monkeypatch, tmp_path
):
    log = []
    monkeypatch.setattr(worker, "get_current_job", lambda: _Job(log))
    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: log.append("punch"))
    disk = _inflated(tmp_path / "d.qcow2")
    worker.dig_holes(str(disk))
    assert log[:2] == [("meta", {"dig_holes_punch": "started"}), "punch"]


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CalledProcessError(
            1,
            ["fallocate"],
            output="fallocate: fallocate failed: Operation not supported",
        ),
        subprocess.CalledProcessError(
            1, ["fallocate"], stderr=b"fallocate failed: Operation not supported"
        ),
    ],
    ids=["wired", "no-job"],
)
def test_a_filesystem_that_cannot_punch_says_so(worker, monkeypatch, tmp_path, failure):
    from isardvdi_common.lib.storage.zeros import DIG_HOLES_UNSUPPORTED

    def refuse(cmd):
        raise failure

    monkeypatch.setattr(worker, "_run_cancellable", refuse)
    with pytest.raises(RuntimeError, match=DIG_HOLES_UNSUPPORTED):
        worker.dig_holes(str(_inflated(tmp_path / "d.qcow2")))


def test_an_unwritten_punch_the_filesystem_refuses_says_so(
    worker, monkeypatch, tmp_path
):
    import errno

    from isardvdi_common.lib.storage import zeros

    def refuse(path):
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    monkeypatch.setattr(worker, "_run_cancellable", lambda cmd: 0)
    monkeypatch.setattr(zeros, "punch_unwritten", refuse)
    with pytest.raises(RuntimeError, match=zeros.DIG_HOLES_UNSUPPORTED):
        worker.dig_holes(str(_inflated(tmp_path / "d.qcow2")))


def test_any_other_failure_is_raised_as_it_is(worker, monkeypatch, tmp_path):
    def fail(cmd):
        raise subprocess.CalledProcessError(1, cmd, output="No space left on device")

    monkeypatch.setattr(worker, "_run_cancellable", fail)
    with pytest.raises(subprocess.CalledProcessError):
        worker.dig_holes(str(_inflated(tmp_path / "d.qcow2")))


def _preallocated(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        os.pwrite(fd, b"\xab" * MIB, 0)
        os.posix_fallocate(fd, MIB, 16 * MIB)
        os.pwrite(fd, b"\xcd" * MIB, 17 * MIB)
        os.fsync(fd)
    finally:
        os.close(fd)
    return str(path)


def _reports_unwritten(path):
    from isardvdi_common.lib.storage import zeros

    fd = os.open(path, os.O_RDONLY)
    try:
        size = os.fstat(fd).st_size
        return any(
            f & zeros.FIEMAP_EXTENT_UNWRITTEN
            for logical, _, f in zeros.fiemap(fd)
            if logical < size
        )
    except OSError:
        return False
    finally:
        os.close(fd)


@pytest.mark.skipif(
    not _fallocate_digs_holes(), reason="this fallocate has no --dig-holes"
)
@pytest.mark.parametrize("verify", [False, True])
def test_a_dig_gives_back_the_preallocation_too(worker, tmp_path, verify):
    disk = _preallocated(tmp_path / "d.qcow2")
    if not _reports_unwritten(disk):
        pytest.skip("this filesystem reports no unwritten extents through FIEMAP")
    result = worker.dig_holes(disk, verify=verify)
    assert result["reclaimed"] >= 16 * MIB
    assert not _reports_unwritten(disk)
    assert result["verified"] is verify


def test_zero_scan_counts_the_file(worker, monkeypatch, tmp_path):
    from isardvdi_common.lib.storage import zeros

    disk = _inflated(tmp_path / "d.qcow2")
    monkeypatch.setattr(zeros, "scan_zeros", lambda path: {"reclaimable_bytes": 7})
    assert worker.zero_scan(str(disk)) == {"reclaimable_bytes": 7}


def test_zero_scan_refuses_a_file_a_guest_holds_open(worker, monkeypatch, tmp_path):
    monkeypatch.setattr(
        worker, "_storage_qcow", lambda: _qcow(True, 'Failed to get "write" lock')
    )
    with pytest.raises(RuntimeError, match="in use by a hypervisor"):
        worker.zero_scan(str(_inflated(tmp_path / "d.qcow2")))


def test_zero_scan_of_a_missing_file_fails(worker, tmp_path):
    with pytest.raises(RuntimeError, match="does not exist"):
        worker.zero_scan(str(tmp_path / "gone.qcow2"))
