# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for the sparsify-backup classifier in the `storage` CLI
(_classify_non_qcow2_files).

The hazard: the classifier decides whether a `*.sparsify-backup` recovery copy
is deletable by running `qemu_img_check(canonical)`, which is `qemu-img check
-U`. `-U` reads straight through a held lock, so a canonical that is currently
locked (a running sparsify/convert mid-write, or a VM) is reported clean and its
in-flight backup would be deleted. This is the same lock-vs-corruption confusion
the sparsify recovery trap fixes, in the consumer that acts on the file the trap
leaves behind.

These tests drive the real classifier against a real qemu-io lock holder.
Requires qemu-img and qemu-io (available in the isard-storage container).
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import time
from importlib.machinery import SourceFileLoader

import pytest

_UTILS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORAGE_CLI = os.path.join(_UTILS_DIR, "storage")

pytestmark = pytest.mark.skipif(
    not (shutil.which("qemu-img") and shutil.which("qemu-io")),
    reason="qemu-img and qemu-io are required (run in the isard-storage container)",
)


def _load_storage_cli():
    import sys

    if _UTILS_DIR not in sys.path:
        sys.path.insert(0, _UTILS_DIR)
    loader = SourceFileLoader("storagecli", _STORAGE_CLI)
    spec = importlib.util.spec_from_loader("storagecli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


storagecli = _load_storage_cli()


def _make_qcow2(path):
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", path, "64M"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["qemu-io", "-c", "write -P 0x11 0 1M", "-f", "qcow2", path],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class _Holder:
    """Hold a qcow2's write lock with a live qemu-io, using the lock-free
    prompt readiness signal (no competing qemu-img check)."""

    def __init__(self, path):
        self.proc = subprocess.Popen(
            ["qemu-io", "-f", "qcow2", path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # wait for the "qemu-io>" prompt: it is printed only after the image is
        # open and the lock taken, and reading it takes no lock of our own
        deadline = time.time() + 30
        buf = ""
        while time.time() < deadline:
            ch = self.proc.stdout.read(1)
            if not ch:
                break
            buf += ch
            if "qemu-io>" in buf:
                return
        self.close()
        raise RuntimeError("qemu-io holder never reached its prompt")

    def close(self):
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write("quit\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def _classify_one(backup_path, db_lookup=None):
    dead, unknown = storagecli._classify_non_qcow2_files(
        [backup_path], {"reverse_map": {}}, db_storage_lookup=db_lookup
    )
    return dead, unknown


def test_locked_canonical_keeps_backup():
    """THE hazard: a locked canonical cannot be proven at rest, so its backup
    must be kept (unknown), never marked dead. Fails on the unfixed classifier,
    which trusts qemu-img check -U reading through the lock."""
    with tempfile.TemporaryDirectory() as d:
        canonical = os.path.join(d, "disk.qcow2")
        backup = canonical + ".sparsify-backup"
        _make_qcow2(canonical)
        shutil.copyfile(canonical, backup)
        db_lookup = {canonical: {"id": "disk", "status": "ready"}}
        holder = _Holder(canonical)
        try:
            dead, unknown = _classify_one(backup, db_lookup)
        finally:
            holder.close()
        assert backup in unknown, (dead, unknown)
        assert backup not in dead, (dead, unknown)


def test_clean_ready_unlocked_canonical_deletes_backup():
    """Positive control: a clean, unlocked, ready canonical still lets the
    backup be reclaimed, so the lock guard does not over-keep."""
    with tempfile.TemporaryDirectory() as d:
        canonical = os.path.join(d, "disk.qcow2")
        backup = canonical + ".sparsify-backup"
        _make_qcow2(canonical)
        shutil.copyfile(canonical, backup)
        db_lookup = {canonical: {"id": "disk", "status": "ready"}}
        dead, unknown = _classify_one(backup, db_lookup)
        assert backup in dead, (dead, unknown)
        assert backup not in unknown, (dead, unknown)


def test_corrupt_canonical_keeps_backup():
    """A corrupt (but unlocked) canonical is not provably clean -> keep."""
    with tempfile.TemporaryDirectory() as d:
        canonical = os.path.join(d, "disk.qcow2")
        backup = canonical + ".sparsify-backup"
        _make_qcow2(canonical)
        shutil.copyfile(canonical, backup)
        # wreck the L1 table -> qemu-img check reports corruption (rc 2)
        with open(canonical, "r+b") as f:
            f.seek(196608)
            f.write(os.urandom(4096))
        db_lookup = {canonical: {"id": "disk", "status": "ready"}}
        dead, unknown = _classify_one(backup, db_lookup)
        assert backup in unknown, (dead, unknown)
        assert backup not in dead, (dead, unknown)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
