#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reconcile a storage pool's files against the storage/media table.

This is the automatic companion to the manual ``storage space`` report: it
reads each file's allocated size (``stat`` ``st_blocks*512``) and, for qcow2,
its virtual size and dirty/corrupt bits from the header (no ``qemu-img``), reads
the DB rows for the pool through apiv4 (never RethinkDB directly), and sorts the
differences into classes. Only the size drift of ``ready`` rows is safe to
correct automatically, and only through the product's own re-measure path; the
rest is reported for an operator to act on.

The classification here is pure (no I/O): the scan and the apiv4 reads happen in
``scan_pool`` / the caller, so the decision logic is unit-testable with fixtures.
"""

import os
from typing import Dict, Iterable, List, Optional, Sequence

from storage_lib import qcow_header, space

#: Default drift that counts as real (matches the manual report's threshold).
DEFAULT_DRIFT_BYTES = space.DEFAULT_DRIFT_BYTES
#: Files under a path containing this segment are the recycle bin's own copies,
#: never "rowless" leftovers.
DELETED_DIR = space.DELETED_DIR


def scan_file(path: str) -> dict:
    """``stat`` + qcow2 header for one file. Never raises for a non-qcow2 or an
    unreadable header: media/raw files simply carry no virtual size or flags."""
    st = os.stat(path)
    info = {
        "path": path,
        "allocated": space.allocated(st),
        "apparent": st.st_size,
        "dev": st.st_dev,
        "ino": st.st_ino,
        "virtual_size": None,
        "dirty": False,
        "corrupt": False,
        "backing_file": None,
        "header_error": None,
    }
    try:
        header = qcow_header.read_header(path)
    except (qcow_header.Qcow2HeaderError, OSError) as exc:
        info["header_error"] = str(exc)
    else:
        info["virtual_size"] = header.virtual_size
        info["dirty"] = header.dirty
        info["corrupt"] = header.corrupt
        info["backing_file"] = header.backing_file
    return info


def scan_pool(
    directories: Sequence[str],
    max_files: Optional[int] = None,
    deadline: Optional[float] = None,
    clock=None,
) -> Dict[str, dict]:
    """Walk ``directories`` and ``scan_file`` each regular file, budgeted.

    ``max_files`` caps the number scanned; ``deadline`` (a monotonic timestamp)
    caps the wall-clock. The caller sets nice/ionice before calling. Returns
    ``{path: scan_file(path)}`` and a ``_budget_hit`` sentinel key when a budget
    stopped the walk early.
    """
    import time as _time

    clock = clock or _time.monotonic
    scanned: Dict[str, dict] = {}
    budget_hit = False
    for directory in directories:
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if max_files is not None and len(scanned) >= max_files:
                    budget_hit = True
                    break
                if deadline is not None and clock() >= deadline:
                    budget_hit = True
                    break
                path = os.path.join(root, name)
                try:
                    if not os.path.isfile(path):
                        continue
                    scanned[path] = scan_file(path)
                except OSError:
                    continue
            if budget_hit:
                break
        if budget_hit:
            break
    scanned["_budget_hit"] = budget_hit  # type: ignore[assignment]
    return scanned


def _under_pool(path: str, pool_prefixes: Sequence[str]) -> bool:
    return any(path.startswith(prefix) for prefix in pool_prefixes)


def _is_live(row: dict) -> bool:
    """A row that should have a file of ``db_size`` on disk: a ``ready`` storage
    disk, or a finished ``Downloaded`` media."""
    if row.get("kind") == "media":
        return row.get("status") == "Downloaded"
    return row.get("status") == "ready"


def classify(
    rows: Iterable[dict],
    scanned: Dict[str, dict],
    pool_prefixes: Sequence[str],
    threshold: int = DEFAULT_DRIFT_BYTES,
) -> Dict[str, List[dict]]:
    """Sort a pool's files/rows into reconciliation classes.

    ``rows``: the DB rows assigned to this pool (from apiv4), each with
        ``id``, ``kind`` (``storage``/``media``), ``path``, ``status`` and
        ``db_size`` (``qemu-img-info.actual-size`` for storage, the media's
        ``progress.total_bytes``).
    ``scanned``: ``{path: scan_file(...)}`` for the files found under the pool.
    ``pool_prefixes``: the directory prefixes this pool owns.

    Classes:
      * ``size_drift`` -- ready rows whose file allocates more/less than the DB
        records, beyond ``threshold``. The ONLY class corrected automatically.
      * ``row_without_file`` -- ready rows whose file is missing.
      * ``row_on_other_pool`` -- rows whose recorded path is not under this pool.
      * ``file_without_row`` -- files under the pool with no DB row.
      * ``dirty_or_corrupt`` -- files the qcow2 header flags as dirty/corrupt.
    """
    files = {p: s for p, s in scanned.items() if p != "_budget_hit"}
    by_path = {r["path"]: r for r in rows if r.get("path")}

    out: Dict[str, List[dict]] = {
        "size_drift": [],
        "row_without_file": [],
        "row_on_other_pool": [],
        "file_without_row": [],
        "dirty_or_corrupt": [],
    }

    for row in rows:
        path = row.get("path")
        if not path:
            continue
        if not _under_pool(path, pool_prefixes):
            out["row_on_other_pool"].append(
                {
                    "id": row["id"],
                    "kind": row.get("kind"),
                    "path": path,
                    "status": row.get("status"),
                }
            )
            continue
        scan = files.get(path)
        if scan is None:
            if _is_live(row):
                out["row_without_file"].append(
                    {"id": row["id"], "kind": row.get("kind"), "path": path}
                )
            continue
        if _is_live(row):
            db = int(row.get("db_size") or 0)
            real = scan["allocated"]
            if abs(real - db) > threshold:
                out["size_drift"].append(
                    {
                        "id": row["id"],
                        "kind": row.get("kind"),
                        "path": path,
                        "db_size": db,
                        "real_size": real,
                        "drift": real - db,
                        "db_virtual_size": row.get("virtual_size"),
                        "header_virtual_size": scan["virtual_size"],
                    }
                )

    for path, scan in files.items():
        if path not in by_path and DELETED_DIR not in path:
            out["file_without_row"].append(
                {"path": path, "allocated": scan["allocated"]}
            )
        if scan["dirty"] or scan["corrupt"]:
            out["dirty_or_corrupt"].append(
                {
                    "path": path,
                    "dirty": scan["dirty"],
                    "corrupt": scan["corrupt"],
                    "id": by_path.get(path, {}).get("id"),
                }
            )

    out["size_drift"].sort(key=lambda m: -abs(m["drift"]))
    out["file_without_row"].sort(key=lambda m: -m["allocated"])
    return out


def correctable_ids(classified: Dict[str, List[dict]]) -> List[str]:
    """The storage ids whose ready-row size drift the product may re-measure."""
    return [
        d["id"]
        for d in classified.get("size_drift", [])
        if d.get("kind") == "storage" and d.get("id")
    ]


def drift_metrics(pool_id: str, classified: Dict[str, List[dict]]) -> Dict[str, dict]:
    """Per-pool bytes + counts per class, ready for a gauge exporter."""
    sd = classified.get("size_drift", [])
    return {
        "pool": pool_id,
        "size_drift_files": len(sd),
        "size_drift_bytes": sum(abs(d["drift"]) for d in sd),
        "row_without_file": len(classified.get("row_without_file", [])),
        "row_on_other_pool": len(classified.get("row_on_other_pool", [])),
        "file_without_row_files": len(classified.get("file_without_row", [])),
        "file_without_row_bytes": sum(
            d["allocated"] for d in classified.get("file_without_row", [])
        ),
        "dirty_or_corrupt": len(classified.get("dirty_or_corrupt", [])),
    }
