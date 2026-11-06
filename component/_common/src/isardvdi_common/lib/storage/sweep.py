# SPDX-License-Identifier: AGPL-3.0-or-later

"""Selection and budget for the nightly storage pending-actions sweep."""

from isardvdi_common.lib.storage.actions import DISK_ACTIONS

#: Presentation defaults for the opt-in sweep config block. Off unless an admin
#: turns it on, mirroring the migration's own opt-in window/budget model.
SWEEP_DEFAULTS = {
    "enabled": False,
    "hour": 4,
    "minute": 0,
    "max_disks": 50,
    "max_bytes": 0,  # 0 == no byte cap
    "sparsify": False,
    "dig_holes": False,
    "repair_leaks": False,
    "check_integrity": False,
    "zero_scan": False,
    "detect": False,  # read-only integrity detection (L0-L3), records pending_actions
    "check_max_age_days": 30,
    # A base that only templates use is dug with its descendants reading it; off
    # until an admin turns it on, and at most max_bases of them a pass.
    "dig_bases_with_children": False,
    "max_bases": 2,
}

#: Sweep action -> the pending-action index it reads. check_integrity has no
#: mark (it selects ready disks by last-checked age); the integrity check wires it.
SWEEP_PENDING_ACTION = {
    "sparsify": "sparsify",
    "dig_holes": "dig_holes",
    "repair_leaks": "repair_leaks",
}

#: How many times an action reads the whole file: a verified dig hashes it before and after.
SWEEP_READ_PASSES = {"dig_holes": 3}

#: Actions whose candidates must have no child; the value counts deleted children too.
SWEEP_SKIPS_PARENTS = {
    "sparsify": False,
    "dig_holes": True,
    "repair_leaks": False,
    "zero_scan": True,
}

#: Rows one action may examine per pass, as a multiple of max_disks (or flat when uncapped).
SWEEP_EXAMINE_FACTOR = 10
SWEEP_EXAMINE_UNCAPPED = 10_000

# the status_zeros_due index embeds this value: changing it needs an index rebuild
ZEROS_RESCAN_GROWTH_BYTES = 256 * 1024 * 1024


def _supersedes(action):
    return getattr(DISK_ACTIONS.get(action), "supersedes", ())


def sweep_order():
    """The mark-driven sweep actions, each before every action it supersedes."""
    actions = list(SWEEP_PENDING_ACTION)
    superseded = {s for a in actions for s in _supersedes(a)}
    return [a for a in actions if a not in superseded] + [
        a for a in actions if a in superseded
    ]


def superseding_marks(action, enabled):
    """Marks that pre-empt ``action`` on a disk this pass, given the enabled actions."""
    return {other for other in enabled if action in _supersedes(other)}


def bytes_read(action, actual_size):
    """What ``action`` reads from a file of ``actual_size`` bytes."""
    return int(actual_size or 0) * SWEEP_READ_PASSES.get(action, 1)


def examine_cap(max_disks):
    """The hard cap on rows one sweep action examines in a pass."""
    return max_disks * SWEEP_EXAMINE_FACTOR if max_disks else SWEEP_EXAMINE_UNCAPPED


def select_within_budget(candidates, max_disks=None, max_bytes=None):
    """Pick, from oldest-first ``candidates`` ({id, size_bytes, started,
    has_children}), the disks a single sweep pass may act on: never one that has
    descendants (the red line -- a write action must not rewrite a template whose
    children back onto it), skip one a Started desktop holds (its file is
    live), stop once ``max_disks`` are chosen, and never let the running total
    exceed ``max_bytes``. ``None`` on either budget means no cap; the caller
    enqueues the returned ids and sets ``has_children`` only for the write actions
    (never for read-only check_integrity). Pure — no DB, no queue."""
    selected, skipped_started, skipped_budget, skipped_has_descendants = [], [], [], []
    used_bytes = 0
    for candidate in candidates:
        if candidate.get("has_children"):
            # RED LINE: excluded before it can spend budget or be enqueued.
            skipped_has_descendants.append(candidate["id"])
            continue
        if max_disks is not None and len(selected) >= max_disks:
            skipped_budget.append(candidate["id"])
            continue
        if candidate.get("started"):
            skipped_started.append(candidate["id"])
            continue
        size = int(candidate.get("size_bytes") or 0)
        if max_bytes is not None and used_bytes + size > max_bytes:
            skipped_budget.append(candidate["id"])
            continue
        selected.append(candidate["id"])
        used_bytes += size
    return {
        "selected": selected,
        "skipped_started": skipped_started,
        "skipped_budget": skipped_budget,
        "skipped_has_descendants": skipped_has_descendants,
        "used_bytes": used_bytes,
    }
