# SPDX-License-Identifier: AGPL-3.0-or-later

"""What stops a user's desktop disk, and which fix answers each problem."""

from dataclasses import dataclass

from isardvdi_common.lib.storage import actions as disk_actions

#: the ``found_by`` of a mark recorded when a user action on a desktop hit the problem
FOUND_BY_INTERACTIVE = "a user action on the desktop"

CHECK = "check"
CHECK_CHAIN = "check_backing_chain"
REPAIR_LEAKS = "repair_leaks"
REPAIR_ALL = "repair_all"
DIG_HOLES = "dig_holes"
SPARSIFY = "sparsify"

#: each fix: the registry action, its repair mode, the task it queues and the mark that records it
FIXES = {
    CHECK: {
        "action": "check_integrity",
        "task": "storage_check",
        "mark": "check_integrity",
    },
    CHECK_CHAIN: {
        "action": "check_backing_chain",
        "task": "qemu_img_info_backing_chain",
        "mark": None,
    },
    REPAIR_LEAKS: {
        "action": "repair",
        "what": "leaks",
        "task": "qemu_img_check_repair",
        "mark": "repair_leaks",
    },
    REPAIR_ALL: {
        "action": "repair",
        "what": "all",
        "task": "qemu_img_check_repair",
        "mark": None,
    },
    DIG_HOLES: {"action": "dig_holes", "task": "dig_holes", "mark": "dig_holes"},
    SPARSIFY: {"action": "sparsify", "task": "sparsify", "mark": "sparsify"},
}

#: the order quick fixes run in: one task per disk at a time, the rest are recorded
QUICK_ORDER = (REPAIR_LEAKS, CHECK_CHAIN, CHECK)


def is_costly(fix):
    """Whether ``fix`` needs an admin or an allowed user to run interactively."""
    entry = FIXES[fix]
    return disk_actions.is_costly(entry["action"], entry.get("what"))


@dataclass(frozen=True)
class Problem:
    code: str
    fix: str | None
    blocks_start: bool


STATUS_PROBLEMS = {
    "maintenance": [Problem("storage_busy", None, True)],
    "creating": [Problem("storage_busy", None, True)],
    "damaged": [
        Problem("storage_damaged", CHECK, True),
        Problem("storage_damaged", REPAIR_ALL, True),
    ],
    "broken_chain": [Problem("storage_broken_chain", CHECK_CHAIN, True)],
}

PENDING_PROBLEMS = {
    "repair_leaks": Problem("storage_leaks", REPAIR_LEAKS, False),
    "check_integrity": Problem("storage_check_due", CHECK, False),
    "check_inconclusive": Problem("storage_check_inconclusive", CHECK, False),
    "dig_holes": Problem("storage_zeros", DIG_HOLES, False),
    "sparsify": Problem("storage_grown", SPARSIFY, False),
    "review_damage": Problem("storage_review_damage", None, True),
    "rebase_backing": Problem("storage_rebase_backing", None, True),
    "review_coherence": Problem("storage_review_coherence", None, False),
    "review_dependents": Problem("storage_review_dependents", None, False),
}


def diagnose(storage):
    """Every problem of one storage row, the blocking ones first, one per fix."""
    status = storage.get("status")
    found = []
    if status in STATUS_PROBLEMS:
        found += STATUS_PROBLEMS[status]
    elif status not in (None, "ready"):
        found.append(Problem("storage_unavailable", None, True))
    for action in storage.get("pending_actions") or {}:
        if action in PENDING_PROBLEMS:
            found.append(PENDING_PROBLEMS[action])
    if status == "damaged" and any(p.fix == REPAIR_LEAKS for p in found):
        found = [
            p for p in found if not (p.code == "storage_damaged" and p.fix == CHECK)
        ]
    unique, seen = [], set()
    for problem in found:
        key = problem.fix or problem.code
        if key not in seen:
            seen.add(key)
            unique.append(problem)
    return sorted(unique, key=lambda p: not p.blocks_start)


def mode(problem):
    """How a problem is handled: wait for the disk, a quick or costly fix, or an admin."""
    if problem.code == "storage_busy":
        return "wait"
    if problem.fix is None:
        return "admin"
    return "costly" if is_costly(problem.fix) else "quick"
