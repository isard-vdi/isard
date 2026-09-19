#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pure classification of table-vs-pool coherence into the eight casuistics.

The gathering (DB query, pool scan, header reads, domain liveness) lives in the
``storage`` CLI; everything here is a pure function of its normalised result, so
the classifier -- and above all the "sustains a live disk" relation nobody else
computes -- is exercised on synthetic data without a database or a filesystem.
"""

import os
from pathlib import Path

from isardvdi_common.lib.storage.paths import RECYCLE_BIN_DIR

from .qcow import uuid_from_path

# Statuses that make a disk's file "live": still serving, or paused mid-op.
LIVE_STATUSES = ("ready", "maintenance")


def _norm(path):
    return os.path.normpath(path) if path else path


def _in_bin(path):
    return RECYCLE_BIN_DIR in Path(path).parts


def best_file_by_uuid(disk_files):
    """Index disk files by uuid, preferring the live copy over a binned one.

    A soft-deleted disk keeps its name in a ``deleted/`` copy beside the live
    one, so the same uuid can appear twice; the live copy always wins so the
    chain is resolved against the file a guest actually reads.
    """
    index = {}
    for df in disk_files:
        u = df.get("uuid")
        if not u:
            continue
        cur = index.get(u)
        if cur is None or (_in_bin(cur["path"]) and not _in_bin(df["path"])):
            index[u] = df
    return index


def sustain_relation(disk_files, live_uuids):
    """Map each present file uuid to the set of live uuids that read through it.

    Walks every live file's backing chain by uuid (headers, not qemu-img), so a
    parent is reported as sustaining a live disk however far down the chain it
    sits. The walk stops at an absent or unreadable ancestor -- that break is a
    casuistic in its own right, not a reason to lose the relation above it.
    """
    file_by_uuid = best_file_by_uuid(disk_files)
    parent_of = {u: f.get("backing_uuid") for u, f in file_by_uuid.items()}
    relation = {}
    for start in live_uuids:
        if start not in file_by_uuid:
            continue
        seen = set()
        cur = parent_of.get(start)
        depth = 0
        while cur and cur not in seen and depth < 200:
            seen.add(cur)
            if cur in file_by_uuid:
                relation.setdefault(cur, set()).add(start)
            cur = parent_of.get(cur)
            depth += 1
    return relation


def live_uuids_from_rows(rows, disk_files):
    """Uuids whose row is live AND whose file is present (a live *file*)."""
    file_by_uuid = best_file_by_uuid(disk_files)
    return {r["id"] for r in rows if r.get("id") in file_by_uuid and r.get("live")}


def uuids_sustaining_live(disk_files, live_uuids):
    """The uuids of files that back at least one live disk (cleanup's guard)."""
    return set(sustain_relation(disk_files, live_uuids))


def uuids_needed_by_live(disk_files, live_uuids):
    """Uuids a live disk depends on: the live disks themselves and every file
    they read through. Deleting any of these breaks a working desktop."""
    return set(live_uuids) | uuids_sustaining_live(disk_files, live_uuids)


def deletable_after_live_guard(deletable, disk_files, live_uuids):
    """Drop from *deletable* every path a live disk needs, by uuid.

    A file is protected when it IS a live disk (ready/maintenance with a domain)
    or when it backs one, wherever the file sits. Resolving support by uuid
    protects a parent even when a live child's stored backing path is stale --
    the exact residue move_disks left, and what a path-keyed dependency map
    misses. Returns ``(kept, protected)`` as sets.
    """
    needed = uuids_needed_by_live(disk_files, live_uuids)
    uuid_by_path = {df["path"]: df.get("uuid") for df in disk_files}
    kept, protected = set(), set()
    for p in deletable:
        u = uuid_by_path.get(p) or uuid_from_path(p)
        (protected if u in needed else kept).add(p)
    return kept, protected


def classify_storage_consistency(
    rows, disk_files, check_errors=None, deferred_jobs=None
):
    """Contrast storage rows with on-disk files and split into the casuistics.

    :param rows: storage rows as ``{"id", "status", "path", "parent", "live"}``;
        ``path`` is the DB-expected ``directory_path/id.type`` and ``live`` is
        precomputed from domains + recycle_bin (status in LIVE_STATUSES and a
        non-binned domain uses the id).
    :param disk_files: one dict per qcow2 on disk, as produced by
        ``qcow.build_backing_index`` plus a ``uuid`` key:
        ``{"path", "uuid", "size", "backing_raw", "backing_uuid", "readable"}``.
    :param check_errors: optional ``{path: info}`` from a qemu-img check pass
        (casuistic 6, only when ``--check`` is given).
    :param deferred_jobs: optional list of deferred-job dicts (casuistic 8, only
        when a table is available); ``ttl<0`` or no ``expires`` means no expiry.
    :return: dict keyed by casuistic with a list of items each.
    """
    rows_by_uuid = {r["id"]: r for r in rows if r.get("id")}
    file_by_uuid = best_file_by_uuid(disk_files)
    live = live_uuids_from_rows(rows, disk_files)
    relation = sustain_relation(disk_files, live)

    c1 = []  # file on disk with no row at all
    c2 = []  # ready row, file gone
    c3 = []  # ready row, file at another pool
    c4a = []  # deleted row whose file sustains live disks
    c4bc = []  # deleted row, file present, no live dependents
    c5 = []  # parent missing (chain break)
    c5b = []  # parent displaced (recoverable by rebase)
    c5c = []  # parent link broken in the row while the file chain is fine
    c7 = []  # non_existing rows

    for r in rows:
        rid, status, dbpath = r.get("id"), r.get("status"), r.get("path")
        f = file_by_uuid.get(rid)
        if status == "ready":
            if f is None:
                c2.append({"id": rid, "path": dbpath})
            elif dbpath and _norm(f["path"]) != _norm(dbpath):
                c3.append(
                    {
                        "id": rid,
                        "db_path": dbpath,
                        "actual_path": f["path"],
                        "size": f.get("size", 0),
                    }
                )
        elif status == "deleted":
            if f is not None:
                sustains = sorted(relation.get(rid, ()))
                item = {"id": rid, "path": f["path"], "size": f.get("size", 0)}
                if sustains:
                    item["sustains"] = sustains
                    item["sustains_count"] = len(sustains)
                    c4a.append(item)
                else:
                    c4bc.append(item)
        elif status == "non_existing":
            c7.append({"id": rid, "path": dbpath})

    for df in disk_files:
        p, u = df["path"], df.get("uuid")
        if u is None or u not in rows_by_uuid:
            c1.append({"path": p, "uuid": u, "size": df.get("size", 0)})
        if _in_bin(p):
            continue
        braw = df.get("backing_raw")
        if not braw:
            continue
        buuid = df.get("backing_uuid")
        parent = file_by_uuid.get(buuid) if buuid else None
        if parent is None:
            c5.append(
                {
                    "path": p,
                    "uuid": u,
                    "size": df.get("size", 0),
                    "backing_raw": braw,
                    "backing_uuid": buuid,
                }
            )
        elif _norm(parent["path"]) != _norm(braw):
            c5b.append(
                {
                    "path": p,
                    "uuid": u,
                    "size": df.get("size", 0),
                    "backing_raw": braw,
                    "found_at": parent["path"],
                }
            )

    for df in disk_files:
        p, u = df["path"], df.get("uuid")
        if _in_bin(p):
            continue
        r = rows_by_uuid.get(u)
        hdr = df.get("backing_uuid")
        backing_row = rows_by_uuid.get(hdr) if hdr else None
        if not r or hdr not in file_by_uuid:
            continue
        if backing_row is None or backing_row.get("status") not in LIVE_STATUSES:
            continue
        if r.get("parent") == hdr:
            continue
        c5c.append(
            {
                "id": u,
                "path": p,
                "size": df.get("size", 0),
                "registered_parent": r.get("parent"),
                "real_backing_uuid": hdr,
                "real_backing_path": file_by_uuid[hdr]["path"],
                "backing_row_status": backing_row.get("status"),
            }
        )

    c6 = []
    for path, info in (check_errors or {}).items():
        entry = {"path": path, "uuid": uuid_from_path(path)}
        entry.update(info or {})
        c6.append(entry)

    c8 = []
    for job in deferred_jobs or []:
        ttl = job.get("ttl")
        if job.get("expires") is None and (ttl is None or ttl < 0):
            c8.append(job)

    return {
        "c1_file_no_row": c1,
        "c2_ready_no_file": c2,
        "c3_ready_wrong_pool": c3,
        "c4a_deleted_sustains_live": c4a,
        "c4bc_deleted_dead": c4bc,
        "c5_parent_missing": c5,
        "c5b_parent_displaced": c5b,
        "c5c_parent_mislinked": c5c,
        "c6_qcow2_errors": c6,
        "c7_non_existing": c7,
        "c8_deferred_no_expiry": c8,
    }


CASUISTIC_TITLES = {
    "c1_file_no_row": "1 · file on disk with no row",
    "c2_ready_no_file": "2 · ready row, file missing",
    "c3_ready_wrong_pool": "3 · ready row, file in another pool",
    "c4a_deleted_sustains_live": "4A · deleted row whose file SUSTAINS live disks",
    "c4bc_deleted_dead": "4B/4C · deleted row, no live dependents",
    "c5_parent_missing": "5 · parent missing (chain break)",
    "c5b_parent_displaced": "5b · parent displaced (rebase recoverable)",
    "c5c_parent_mislinked": "5c · parent link broken in row, file chain intact",
    "c6_qcow2_errors": "6 · qcow2 with leaks/errors",
    "c7_non_existing": "7 · non_existing rows",
    "c8_deferred_no_expiry": "8 · deferred jobs with no expiry",
}
