# SPDX-License-Identifier: AGPL-3.0-or-later
"""Direct RethinkDB access for the storage CLI.

Most subcommands use the API (`storage_lib.api`) and stay read-only against
the application surface. The `db-cleanup` subcommand needs to (a) detect
malformed `storage` rows the API can't surface in a useful shape, and (b)
optionally delete them. Both operations are tightly scoped:

- We only ever look at the `storage`, `domains`, and `recycle_bin` tables.
- We refuse to delete anything that is referenced by a domain, recycle_bin
  entry, or as a backing-chain parent of another storage.
- Every deletion is preceded by a JSONL dump of the row about to be removed.

Connection assumes the standard isardvdi env: hostname `isard-db`, port
28015, db `isard`. Override via RETHINKDB_HOST / RETHINKDB_PORT / RETHINKDB_DB.
"""

import json
import os
import re
import time
from contextlib import contextmanager

from rethinkdb import r

from .formatting import log

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@contextmanager
def get_conn():
    """Yield a RethinkDB connection to the isard database."""
    conn = None
    try:
        conn = r.connect(
            host=os.environ.get("RETHINKDB_HOST", "isard-db"),
            port=int(os.environ.get("RETHINKDB_PORT", "28015")),
            db=os.environ.get("RETHINKDB_DB", "isard"),
            timeout=20,
        )
        yield conn
    finally:
        if conn is not None:
            conn.close(noreply_wait=False)


def _is_uuid(value):
    return isinstance(value, str) and bool(UUID_RE.match(value))


def find_zombie_storages(conn):
    """Storage rows containing no fields beyond `id`.

    These rows are the residue of `RethinkBase.__init__` auto-creating a stub
    when a Storage(id) call hits a non-existent id. They have no status,
    type, directory_path, status_logs, or qemu-img-info — there is nothing
    to repair, only to remove.
    """
    return list(
        r.table("storage")
        .filter(lambda s: ~s.has_fields("directory_path") & ~s.has_fields("type"))
        .run(conn)
    )


def find_path_shaped_ids(conn):
    """Storage rows whose `id` is a filesystem path string instead of a UUID.

    Caused by upstream code calling `Storage(parent_path)` where the parent
    field was stored as a path. The disk file referenced by the path may
    well exist and be in active use as a backing file; we never delete the
    disk, only the fake row.
    """
    return list(r.table("storage").filter(lambda s: s["id"].match("^/")).run(conn))


def find_storages_with_path_parent(conn):
    """Storage rows whose `parent` field looks like a filesystem path.

    These are not corrupt rows — the `id` is a real UUID and the row has
    proper fields — but the `parent` link is wrong shape. The chain still
    works at the filesystem level (`backing_file=` carries paths), but DB
    queries that join on `parent` produce empty results.

    Reported only; do NOT auto-rewrite. The path string carries the
    information the operator needs to map it back to a UUID by hand.
    """
    return list(
        r.table("storage")
        .filter(
            lambda s: s.has_fields("parent")
            & s["parent"].type_of().eq("STRING")
            & s["parent"].match("^/")
        )
        .pluck("id", "parent", "status", "directory_path", "type")
        .run(conn)
    )


def find_recycle_bin_orphan_disks(conn, on_disk_paths):
    """Recycle-bin entries in `status=deleted` whose disk files still exist.

    `on_disk_paths` is a set of every qcow2 path currently on disk (caller
    supplies it from the regular scan). For each `recycle_bin` entry whose
    `status=="deleted"` we walk its `storages[]` ids and report any whose
    expected path is still on disk — these survived the delete pipeline.
    """
    rb_entries = list(
        r.table("recycle_bin")
        .filter({"status": "deleted"})
        .pluck("id", "accessed", "item_type", "storages")
        .run(conn)
    )
    out = []
    for e in rb_entries:
        residual = []
        for s in e.get("storages") or []:
            sid = s.get("id")
            if not sid:
                continue
            dp = s.get("directory_path") or ""
            stype = s.get("type") or "qcow2"
            expected = f"{dp}/{sid}.{stype}" if dp else None
            if expected and expected in on_disk_paths:
                residual.append({"storage_id": sid, "path": expected})
            else:
                # fallback: try matching by basename uuid in any path
                for p in on_disk_paths:
                    if sid in p:
                        residual.append({"storage_id": sid, "path": p})
                        break
        if residual:
            out.append(
                {
                    "recycle_bin_id": e["id"],
                    "accessed": e.get("accessed"),
                    "item_type": e.get("item_type"),
                    "residual": residual,
                }
            )
    return out


def is_storage_referenced(conn, storage_id):
    """True iff some domain, recycle_bin, or other storage references this id.

    Returns a dict of references for reporting:
        {"by_domains": [...], "by_recycle_bin": [...], "by_storage_parent": [...]}
    """
    refs = {"by_domains": [], "by_recycle_bin": [], "by_storage_parent": []}

    domains = list(
        r.table("domains")
        .filter(
            lambda d: d["create_dict"]["hardware"]["disks"]
            .default([])
            .contains(lambda dd: dd["storage_id"].default(None).eq(storage_id))
        )
        .pluck("id", "name", "kind")
        .limit(5)
        .run(conn)
    )
    refs["by_domains"] = domains

    rcb = list(
        r.table("recycle_bin")
        .filter(
            lambda x: x["storages"]
            .default([])
            .contains(lambda s: s["id"].default(None).eq(storage_id))
        )
        .pluck("id", "status", "item_type")
        .limit(5)
        .run(conn)
    )
    refs["by_recycle_bin"] = rcb

    parents = list(
        r.table("storage")
        .filter({"parent": storage_id})
        .pluck("id", "status")
        .limit(5)
        .run(conn)
    )
    refs["by_storage_parent"] = parents

    return refs


def delete_storage_row(conn, storage_id):
    """Remove a single row from the `storage` table by id. Returns the
    rethinkdb response dict for the operator to inspect.
    """
    return r.table("storage").get(storage_id).delete().run(conn)


def dump_jsonl(records, path):
    """Write a list of dicts to a JSONL file. Returns the count written."""
    n = 0
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            n += 1
    return n


def categorize_zombies(rows):
    """Split zombie rows into UUID-shaped vs path-shaped id buckets."""
    uuid_zombies = []
    path_zombies = []
    other_zombies = []
    for row in rows:
        rid = row.get("id", "")
        if _is_uuid(rid):
            uuid_zombies.append(row)
        elif isinstance(rid, str) and rid.startswith("/"):
            path_zombies.append(row)
        else:
            other_zombies.append(row)
    return uuid_zombies, path_zombies, other_zombies


def now_ts():
    return int(time.time())
