# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `storage` CLI must not delete a recovery copy whose partner is in use.

The hazard: the classifier decided whether a `*.sparsify-backup` was deletable
by running `qemu_img_check(canonical)`, which passes ``-U``. That reads straight
through a held lock, so a canonical being written right now -- a running
sparsify, a convert, a live VM -- answers "clean" and its in-flight backup gets
deleted. Measured against real qemu-img: a live-held image gives rc 0 under
``-U`` and rc 1 without it.

The CLI is a Python script with no suffix, so it is loaded by path. Both helpers
it consults reach qemu-img through one ``subprocess.run``, so replacing that is
enough to model each state -- no qemu binaries, no lock holder, no root, and
nothing to race.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
from importlib.machinery import SourceFileLoader

import pytest

_UTILS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORAGE_CLI = os.path.join(_UTILS_DIR, "storage")


def _load_storage_cli():
    if _UTILS_DIR not in sys.path:
        sys.path.insert(0, _UTILS_DIR)
    loader = SourceFileLoader("storagecli", _STORAGE_CLI)
    spec = importlib.util.spec_from_loader("storagecli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# The CLI imports the generated apiv4 client at module level, and that client is
# produced by codegen rather than carried in a checkout. Skip before the load
# that would fail, so this file never breaks collection for whichever target
# picks it up.
pytest.importorskip(
    "isardvdi_apiv4_client.client",
    reason="the generated apiv4 client is produced by codegen",
)

storagecli = _load_storage_cli()

from storage_lib import qcow  # noqa: E402  -- import after sys.path is set

_CLEAN = "No errors were found on the image.\n"
_LOCK_ERROR = (
    'qemu-img: Could not open: Failed to get shared "write" lock\n'
    "Is another process using the image?\n"
)


class _Ran:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_qemu(monkeypatch, *, locked=False, corrupt=False):
    """Answer as real qemu-img does for the state being modelled.

    The locked case is the load-bearing one: ``check`` carries ``-U`` and reads
    through the lock (rc 0, "no errors"), while ``info`` does not and fails.
    """

    def run(cmd, *args, **kwargs):
        argv = [str(part) for part in cmd]
        if "check" in argv:
            if corrupt:
                return _Ran(returncode=2, stderr="ERROR cluster ... corrupted\n")
            return _Ran(returncode=0, stdout=_CLEAN)
        if "info" in argv:
            if locked:
                raise subprocess.CalledProcessError(
                    1, argv, output="", stderr=_LOCK_ERROR
                )
            return _Ran(returncode=0, stdout="{}")
        return _Ran()

    monkeypatch.setattr(qcow.subprocess, "run", run)


def _pair(directory):
    canonical = os.path.join(directory, "disk.qcow2")
    backup = canonical + ".sparsify-backup"
    for path in (canonical, backup):
        with open(path, "wb") as handle:
            handle.write(b"QFI\xfb" + b"\0" * 64)
    return canonical, backup


def _classify(backup_path, db_lookup=None):
    return storagecli._classify_non_qcow2_files(
        [backup_path], {"reverse_map": {}}, db_storage_lookup=db_lookup
    )


def test_locked_canonical_keeps_backup(monkeypatch):
    """THE hazard: a locked canonical cannot be proven at rest, so its backup
    must be kept, never marked dead. Fails on the unfixed classifier, which
    trusts the lock-bypassing check."""
    with tempfile.TemporaryDirectory() as directory:
        _canonical, backup = _pair(directory)
        _fake_qemu(monkeypatch, locked=True)

        dead, unknown = _classify(backup)

        assert backup in unknown, (dead, unknown)
        assert backup not in dead, (dead, unknown)


def test_clean_ready_unlocked_canonical_deletes_backup(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        _canonical, backup = _pair(directory)
        _fake_qemu(monkeypatch)

        dead, unknown = _classify(backup)

        assert backup in dead, (dead, unknown)
        assert backup not in unknown, (dead, unknown)


def test_corrupt_canonical_keeps_backup(monkeypatch):
    """A backup is exactly what a corrupt canonical needs kept."""
    with tempfile.TemporaryDirectory() as directory:
        _canonical, backup = _pair(directory)
        _fake_qemu(monkeypatch, corrupt=True)

        dead, unknown = _classify(backup)

        assert backup in unknown, (dead, unknown)
        assert backup not in dead, (dead, unknown)


def test_missing_canonical_keeps_backup(monkeypatch):
    """Nothing to compare against: the backup may be the only copy left."""
    with tempfile.TemporaryDirectory() as directory:
        canonical, backup = _pair(directory)
        os.unlink(canonical)
        _fake_qemu(monkeypatch)

        dead, unknown = _classify(backup)

        assert backup in unknown, (dead, unknown)
        assert backup not in dead, (dead, unknown)
