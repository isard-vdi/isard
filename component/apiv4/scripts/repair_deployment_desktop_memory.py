#!/usr/bin/env python3
"""One-shot repair for deployment desktops stored with memory below the engine
minimum (25 MiB).

Restores each affected domain's ``hardware.memory`` (and
``create_dict.hardware.memory``) from its parent deployment's create_dict recipe,
matched by ``tag_desktop_id``. Domains with no deployment, no matching recipe, or
a sub-minimum recipe value are left untouched and logged for manual review.

Dry-run by default; pass ``--apply`` to commit. Idempotent.

Run inside the apiv4 container::

    docker exec -i isard-apiv4 python3 < component/apiv4/scripts/repair_deployment_desktop_memory.py
    docker exec isard-apiv4 python3 /opt/isardvdi/scripts/repair_deployment_desktop_memory.py --apply
"""

import os
import sys

from rethinkdb import r

DB_HOST = os.environ.get("RETHINKDB_HOST", "isard-db")
DB_PORT = int(os.environ.get("RETHINKDB_PORT", "28015"))
DB_NAME = os.environ.get("RETHINKDB_DB", "isard")

# Engine set_memory floor: 25 MiB = 25600 KiB.
MIN_MEMORY_KIB = 25600


def _deployment_memory_for(conn, tag, tag_desktop_id):
    """Correct KiB memory from the deployment's create_dict recipe, or None."""
    if not tag:
        return None
    dep = r.table("deployments").get(tag).run(conn)
    if not dep:
        return None
    for recipe in dep.get("create_dict") or []:
        if recipe.get("tag_desktop_id") == tag_desktop_id:
            return (recipe.get("hardware") or {}).get("memory")
    return None


def _repair(conn, apply_changes):
    fixed = skipped = 0
    candidates = list(
        r.table("domains")
        .filter(lambda d: d["kind"] == "desktop")
        .filter(
            lambda d: d["hardware"]["memory"].default(MIN_MEMORY_KIB) < MIN_MEMORY_KIB
        )
        .pluck("id", "name", "tag", "tag_desktop_id", {"hardware": ["memory"]})
        .run(conn)
    )
    print(f"found {len(candidates)} desktop(s) with memory < {MIN_MEMORY_KIB} KiB")
    for d in candidates:
        did = d["id"]
        cur = d.get("hardware", {}).get("memory")
        correct = _deployment_memory_for(conn, d.get("tag"), d.get("tag_desktop_id"))
        if not isinstance(correct, (int, float)) or correct < MIN_MEMORY_KIB:
            print(
                f"  SKIP {did} ({d.get('name')!r}) mem={cur}: no usable deployment "
                f"recipe memory ({correct!r}); manual review"
            )
            skipped += 1
            continue
        correct = int(correct)
        print(f"  FIX  {did} ({d.get('name')!r}) mem {cur} -> {correct} KiB")
        fixed += 1
        if not apply_changes:
            continue
        r.table("domains").get(did).update(
            {
                "hardware": {"memory": correct},
                "create_dict": {"hardware": {"memory": correct}},
            }
        ).run(conn)
    return fixed, skipped


def main():
    apply_changes = "--apply" in sys.argv[1:]
    conn = r.connect(host=DB_HOST, port=DB_PORT, db=DB_NAME)
    try:
        mode = "APPLY" if apply_changes else "DRY-RUN"
        print(f"=== repair_deployment_desktop_memory [{mode}] ===")
        fixed, skipped = _repair(conn, apply_changes)
        print(f"=== summary: fix={fixed} skip={skipped} (use --apply to commit) ===")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
