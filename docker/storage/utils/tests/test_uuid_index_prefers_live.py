"""A recycle-bin copy must never shadow the live disk in the uuid index.

A soft-deleted disk keeps its filename inside a ``deleted`` directory of its own
pool, so the same uuid exists twice on disk. ``_build_uuid_index`` took the first
path ``rglob`` handed it, which is arbitrary -- and that index is what chain
repair resolves a missing backing file against, so a live disk could be rebased
onto a discarded copy.

Measured on a live multi-node share before the fix: 28 live files resolved to
their recycle-bin copy.
"""

import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1]
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from isardvdi_common.lib.storage.paths import RECYCLE_BIN_DIR  # noqa: E402
from storage_lib.qcow import _build_uuid_index  # noqa: E402

UID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make(tmp_path, *, live=True, binned=True):
    pool = tmp_path / "pool" / "default" / "groups"
    pool.mkdir(parents=True)
    (pool / RECYCLE_BIN_DIR).mkdir()
    if live:
        (pool / f"{UID}.qcow2").write_bytes(b"QFI\xfb")
    if binned:
        (pool / RECYCLE_BIN_DIR / f"{UID}.qcow2").write_bytes(b"QFI\xfb")
    return pool


def test_live_file_wins_over_its_recycle_bin_copy(tmp_path, monkeypatch):
    """Forced into the adversarial order: rglob hands back the bin copy first.

    Real rglob order is filesystem-dependent, so asserting on it would pass by
    luck; the whole defect is that the FIRST path seen used to win.
    """
    pool = _make(tmp_path)

    real_rglob = Path.rglob

    def bin_first(self, pattern):
        found = list(real_rglob(self, pattern))
        return iter(sorted(found, key=lambda f: RECYCLE_BIN_DIR not in f.parts))

    monkeypatch.setattr(Path, "rglob", bin_first)

    resolved = _build_uuid_index([str(tmp_path)])[UID]

    assert resolved == str(pool / f"{UID}.qcow2"), (
        "the uuid resolved to the discarded copy; chain repair would rebase a "
        f"live disk onto it -- got {resolved}"
    )


def test_a_bin_copy_alone_is_still_indexed(tmp_path):
    """With no live file left, the bin copy is the only thing to point at."""
    pool = _make(tmp_path, live=False)

    resolved = _build_uuid_index([str(tmp_path)])[UID]

    assert resolved == str(pool / RECYCLE_BIN_DIR / f"{UID}.qcow2")


def test_a_lone_live_file_is_indexed(tmp_path):
    pool = _make(tmp_path, binned=False)

    assert _build_uuid_index([str(tmp_path)])[UID] == str(pool / f"{UID}.qcow2")
