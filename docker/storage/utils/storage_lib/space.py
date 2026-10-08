#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the storage table says the disks occupy against what the files allocate."""

import os
from collections import defaultdict
from typing import Dict, Iterable, List

DELETED_DIR = "/deleted/"
DEFAULT_DRIFT_BYTES = 64 << 20


def allocated(stat_result) -> int:
    return stat_result.st_blocks * 512


def db_actual_size(row: dict) -> int:
    return int(((row.get("qemu-img-info") or {}).get("actual-size")) or 0)


def size_drift(
    rows: Iterable[dict], fs_lookup: Dict[str, os.stat_result], threshold: int
) -> List[dict]:
    """Ready rows whose recorded size differs from the allocated size by more than ``threshold``."""
    out = []
    for row in rows:
        if row.get("status") != "ready":
            continue
        st = fs_lookup.get(row.get("path"))
        if st is None:
            continue
        db = db_actual_size(row)
        real = allocated(st)
        if abs(real - db) > threshold:
            out.append(
                {
                    "id": row["id"],
                    "path": row["path"],
                    "db_size": db,
                    "real_size": real,
                    "drift": real - db,
                }
            )
    out.sort(key=lambda m: -abs(m["drift"]))
    return out


def space_report(
    rows: Iterable[dict],
    fs_lookup: Dict[str, os.stat_result],
    threshold: int = DEFAULT_DRIFT_BYTES,
) -> dict:
    """Per filesystem: the DB view of ready disks next to what the files allocate, once per inode."""
    rows = list(rows)
    by_path = {r["path"]: r for r in rows if r.get("path")}
    by_inode = defaultdict(list)
    for path, st in fs_lookup.items():
        by_inode[(st.st_dev, st.st_ino)].append(path)
    fs = defaultdict(
        lambda: {
            "db_ready": 0,
            "ready_allocated": 0,
            "ready_apparent": 0,
            "ready_files": 0,
            "deleted_dir": 0,
            "deleted_dir_files": 0,
            "no_row": 0,
            "no_row_files": 0,
            "other_status": 0,
            "other_status_files": 0,
            "sample_path": None,
        }
    )
    for paths in by_inode.values():
        # an alias of a row's own path must not make the file look rowless
        path = next((p for p in sorted(paths) if p in by_path), sorted(paths)[0])
        st = fs_lookup[path]
        acc = fs[st.st_dev]
        acc["sample_path"] = acc["sample_path"] or path
        row = by_path.get(path)
        if DELETED_DIR in path:
            acc["deleted_dir"] += allocated(st)
            acc["deleted_dir_files"] += 1
        elif row is None:
            acc["no_row"] += allocated(st)
            acc["no_row_files"] += 1
        elif row.get("status") == "ready":
            acc["db_ready"] += db_actual_size(row)
            acc["ready_allocated"] += allocated(st)
            acc["ready_apparent"] += st.st_size
            acc["ready_files"] += 1
        else:
            acc["other_status"] += allocated(st)
            acc["other_status_files"] += 1
    return {"filesystems": dict(fs), "drift": size_drift(rows, fs_lookup, threshold)}


def filesystem_usage(path: str) -> dict:
    """Used and free bytes the filesystem itself reports for ``path``."""
    v = os.statvfs(path)
    return {
        "size": v.f_blocks * v.f_frsize,
        "free": v.f_bavail * v.f_frsize,
        "used": (v.f_blocks - v.f_bfree) * v.f_frsize,
    }
