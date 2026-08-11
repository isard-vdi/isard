"""The pool scan must not treat recycle-bin copies as movable disks.

A disk that IsardVDI soft-deletes is not unlinked: the worker renames it into
a bin subdirectory beside it. The scan walks the pool with
``rglob``, so it sees those copies too, and the tool derives the storage id
from the FILE NAME -- which resolves to the LIVE row, wherever that row now
lives. Two things follow, both seen against a live multi-node stack:

  * the same storage id is queued twice, once for the live file and once for
    its recycle-bin copy;
  * when the live row already sits at the destination, apiv4 rejects the move
    with ``already in destination pool path ... to execute rsync operation``,
    and the run reports failures that are not failures.

The existing "deleted" guard elsewhere in the tool checks the storage ROW's
status, which is ``ready`` for these -- so it cannot catch this. The location
is the only signal, so the scan skips the directory.
"""

import importlib.machinery
import importlib.util
import os
from datetime import datetime
from pathlib import Path

import pytest


def _load_move_disks():
    """Load the suffix-less CLI by path, neutralising its start-up mkdirs."""
    path = Path(__file__).resolve().parents[1] / "move_disks"
    spec = importlib.util.spec_from_loader(
        "move_disks", importlib.machinery.SourceFileLoader("move_disks", str(path))
    )
    module = importlib.util.module_from_spec(spec)

    real_makedirs = os.makedirs

    def makedirs_unless_absolute(name, *args, **kwargs):
        if str(name).startswith("/"):
            return None
        return real_makedirs(name, *args, **kwargs)

    os.makedirs = makedirs_unless_absolute
    try:
        spec.loader.exec_module(module)
    finally:
        os.makedirs = real_makedirs
    return module


# The tool imports the generated apiv4 client at module level, and that client
# is produced by codegen rather than carried in a checkout. Skip before the load
# that would fail.
pytest.importorskip(
    "isardvdi_apiv4_client.client",
    reason="the generated apiv4 client is produced by codegen",
)

move_disks = _load_move_disks()


def _pool(root):
    """A pool holding one live disk and one recycle-bin copy of another."""
    live = root / "default" / "groups"
    binned = root / "default" / "groups" / "deleted"
    live.mkdir(parents=True)
    binned.mkdir(parents=True)
    (live / "aaaa.qcow2").write_bytes(b"QFI\xfb" + b"\0" * 64)
    (binned / "bbbb.qcow2").write_bytes(b"QFI\xfb" + b"\0" * 64)
    return live / "aaaa.qcow2", binned / "bbbb.qcow2"


def _scan(root):
    before, after = move_disks.get_sorted_file_paths_by_date(
        str(root), datetime.now().isoformat()
    )
    paths = list(before[0]) + list(after[0])
    return {Path(p[0] if isinstance(p, (tuple, list)) else p).resolve() for p in paths}


def test_scan_skips_the_recycle_bin(tmp_path):
    live, binned = _pool(tmp_path)

    seen = _scan(tmp_path)

    assert live.resolve() in seen, "the live disk must still be scanned"
    assert binned.resolve() not in seen, (
        "a recycle-bin copy was scanned; it resolves to the live row and gets "
        "queued a second time"
    )


def test_scan_keeps_a_disk_whose_name_merely_contains_deleted(tmp_path):
    """Only a `deleted` DIRECTORY is the recycle bin -- not a substring."""
    live = tmp_path / "default" / "groups"
    live.mkdir(parents=True)
    odd = live / "deleted-by-mistake.qcow2"
    odd.write_bytes(b"QFI\xfb" + b"\0" * 64)

    assert odd.resolve() in _scan(tmp_path)
