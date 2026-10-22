# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integrity detection levels: read-only checks that return findings for the
caller to record in ``pending_actions``.

Nothing here opens a file, writes a status or creates a row. Each level takes
facts (database rows, and for the on-disk levels a backing index already built
by :func:`build_backing_index`) and returns ``(storage_id, action, detail)``
findings. ``dependents_of`` is the single engine for "what backs onto this
disk" (D2); no level answers that question any other way.
"""

from isardvdi_common.lib.storage.dependents import dependents_of

#: Statuses the database uses for a disk it treats as gone from service.
GONE_STATUSES = frozenset({"deleted", "orphan", "broken_chain"})


def detect_coherence(rows, *, live_user_ids, storages_used_by_live_domains):
    """L0 - reconcile each row against the database graph, no disk access.

    Flags ``review_coherence`` for a row whose owner no longer exists, or a row
    the database treats as gone that a live desktop still uses.
    """
    used = set(storages_used_by_live_domains)
    live_users = set(live_user_ids)
    findings = []
    for row in rows:
        storage_id = row.get("id")
        reasons = []
        owner = row.get("user_id")
        if owner and owner not in live_users:
            reasons.append(f"owner {owner} no longer exists")
        if row.get("status") in GONE_STATUSES and storage_id in used:
            reasons.append(
                f"a live desktop uses this disk though its status is {row.get('status')}"
            )
        if reasons:
            findings.append((storage_id, "review_coherence", {"reasons": reasons}))
    return findings


def detect_missing_file(rows, backing_index):
    """L1 - a live-status row whose file the scan did not find.

    ``rows`` is ``[{id, status, path}]`` whose ``path`` is inside a pool the
    scan covered, so the caller guarantees an absence here is real and not a
    disk that simply lives in an unscanned pool. Flags ``review_coherence``.
    """
    findings = []
    for row in rows:
        if row.get("status") in GONE_STATUSES:
            continue
        if row["path"] not in backing_index:
            findings.append(
                (
                    row["id"],
                    "review_coherence",
                    {
                        "reason": "the row's file is not in its pool",
                        "path": row["path"],
                    },
                )
            )
    return findings


def detect_broken_chain(rows, backing_index):
    """L2 - a present disk whose backing file the scan cannot find.

    ``backing_index`` must span every enabled pool (a chain can cross pools),
    so a backing absent from it is genuinely gone. Flags ``rebase_backing``
    when the backing's uuid is known (the parent most likely moved) and
    ``review_coherence`` when the reference cannot be resolved at all.
    """
    present_paths = set(backing_index)
    present_uuids = {e["uuid"] for e in backing_index.values() if e.get("uuid")}
    findings = []
    for row in rows:
        entry = backing_index.get(row["path"])
        if not entry or not entry.get("readable"):
            continue
        backing_raw = entry.get("backing_raw")
        if not backing_raw:
            continue
        backing_uuid = entry.get("backing_uuid")
        if backing_raw in present_paths or (
            backing_uuid and backing_uuid in present_uuids
        ):
            continue
        action = "rebase_backing" if backing_uuid else "review_coherence"
        findings.append(
            (
                row["id"],
                action,
                {
                    "reason": "backing file not found in any pool",
                    "backing": backing_raw,
                },
            )
        )
    return findings


def detect_on_disk_dependents(gone_disks, backing_index, *, live_uuids):
    """L3 - a disk the database treats as gone that on-disk disks still back onto.

    ``gone_disks`` is ``[(storage_id, path)]`` for rows in a gone status;
    ``backing_index`` is :func:`build_backing_index` over the pool's files.
    Keeps only dependents whose own uuid is live, and reports (never hides) a
    candidate it could not read. Flags ``review_dependents``.
    """
    live = set(live_uuids)
    findings = []
    for storage_id, path in gone_disks:
        dependents, unreadable = dependents_of(
            path, backing_index, transitive=True, live_uuids=live
        )
        if dependents:
            findings.append(
                (
                    storage_id,
                    "review_dependents",
                    {
                        "path": path,
                        "dependents": dependents,
                        "unreadable": unreadable,
                    },
                )
            )
    return findings
