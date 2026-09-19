# SPDX-License-Identifier: AGPL-3.0-or-later

"""Selection and budget for the nightly storage pending-actions sweep (#4241)."""

#: Presentation defaults for the opt-in sweep config block. Off unless an admin
#: turns it on, mirroring the migration's own opt-in window/budget model.
SWEEP_DEFAULTS = {
    "enabled": False,
    "hour": 4,
    "minute": 0,
    "max_disks": 50,
    "max_bytes": 0,  # 0 == no byte cap
    "sparsify": False,
    "repair_leaks": False,
    "check_integrity": False,
    "check_max_age_days": 30,
}

#: Sweep action -> the pending-action index it reads. check_integrity has no
#: mark (it selects ready disks by last-checked age); it is wired in #4238 ph.3.
SWEEP_PENDING_ACTION = {
    "sparsify": "sparsify",
    "repair_leaks": "repair_leaks",
}


def select_within_budget(candidates, max_disks=None, max_bytes=None):
    """Pick, from oldest-first ``candidates`` ({id, size_bytes, started}), the
    disks a single sweep pass may act on: skip one a Started desktop holds (its
    file is live), stop once ``max_disks`` are chosen, and never let the running
    total exceed ``max_bytes``. ``None`` on either budget means no cap; the
    caller enqueues the returned ids. Pure — no DB, no queue."""
    selected, skipped_started, skipped_budget = [], [], []
    used_bytes = 0
    for candidate in candidates:
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
        "used_bytes": used_bytes,
    }
