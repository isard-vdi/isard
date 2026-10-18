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
