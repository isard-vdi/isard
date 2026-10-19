# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every disk action, what it does to the file, and the one guard that admits it."""

from dataclasses import dataclass
from enum import Enum


class Access(str, Enum):
    """What an action does to THIS disk's file."""

    #: writes, moves, replaces, converts or deletes it
    WRITE = "write"
    #: only reads it
    READ = "read"
    #: makes a new file: a fresh disk, or one backed on (or copied from) this one
    CREATE = "create"


STOPPED = ("Stopped",)
RUNNING = ("Started", "Starting", "Shutting-down", "Stopping", "Paused")


@dataclass(frozen=True)
class DiskAction:
    access: Access
    #: statuses the disk may be in; None when the action has no status precondition
    statuses: tuple = ("ready",)
    status_refusal: str = "storage_not_ready"
    #: statuses every domain using the disk must be in; None when not checked
    domains: tuple = STOPPED
    #: refused while a domain using the disk is running (it holds the file open)
    refuse_running: bool = False
    running_refusal: str = "storage_open_not_checkable"
    children_block: bool = True
    #: children in status ``deleted`` count too: their file may still read this one
    children_include_deleted: bool = False
    #: refused when the disk's ``perms`` lack ``w``
    refuse_read_only: bool = False
    #: refused when any template uses the disk
    refuse_templates: bool = False
    #: refused when no domain uses the disk
    refuse_unused: bool = False


def _reader(**kwargs):
    return DiskAction(
        Access.READ,
        statuses=None,
        domains=None,
        children_block=False,
        **kwargs,
    )


def _fresh():
    return DiskAction(
        Access.CREATE,
        statuses=None,
        domains=None,
        children_block=False,
    )


_WRITER = DiskAction(Access.WRITE)

DISK_ACTIONS = {
    "find": _reader(),
    "check_backing_chain": _reader(),
    "check_integrity": _reader(refuse_running=True),
    "create": _fresh(),
    "download": _fresh(),
    "derive": DiskAction(Access.CREATE, domains=None, children_block=False),
    "move": DiskAction(
        Access.WRITE,
        statuses=("ready", "recycled"),
        status_refusal="storage_invalid_status_for_move",
    ),
    "migrate": DiskAction(
        Access.WRITE, statuses=None, domains=None, children_block=False
    ),
    "purge": DiskAction(
        Access.WRITE, statuses=None, domains=None, children_block=False
    ),
    "delete": DiskAction(Access.WRITE, statuses=None),
    "template_from_desktop": DiskAction(
        Access.WRITE, domains=None, children_block=False
    ),
    "resize": _WRITER,
    "virt_win_reg": _WRITER,
    "sparsify": _WRITER,
    # Rewrites the file in place: only a desktop's own leaf disk, never a base
    # anything reads through, a template or a disk nobody uses.
    "dig_holes": DiskAction(
        Access.WRITE,
        refuse_running=True,
        running_refusal="storage_open_by_running_desktop",
        children_include_deleted=True,
        refuse_read_only=True,
        refuse_templates=True,
        refuse_unused=True,
    ),
    "repair": DiskAction(
        Access.WRITE,
        statuses=("ready", "damaged"),
        status_refusal="storage_invalid_status_for_repair",
        domains=("Stopped", "Failed"),
    ),
    "disconnect": _WRITER,
    "convert": _WRITER,
    "recreate": _WRITER,
    "set_path": _WRITER,
    "delete_path": _WRITER,
    "maintenance": _WRITER,
}

_STATUS_MESSAGES = {
    "storage_invalid_status_for_move": "Storage {id} can only be moved from 'ready' or 'recycled' status. Current status is '{status}'",
    "storage_invalid_status_for_repair": "Storage {id} can only be repaired from 'ready' or 'damaged' status. Current status is '{status}'",
    "storage_not_ready": "Storage {id} must be Ready in order to operate with it. It's actual status is {status}",
}

_RUNNING_MESSAGES = {
    "storage_open_not_checkable": "Storage {id} is open by a running desktop; not checking it.",
    "storage_open_by_running_desktop": "Storage {id} is open by a running desktop; stop it first.",
}


def spec(action):
    """The registry entry for ``action``; a label it does not know is a plain write."""
    return DISK_ACTIONS.get(action, DISK_ACTIONS["maintenance"])


def needs_domains(action):
    """Whether deciding ``action`` reads the domains that use the disk."""
    entry = spec(action)
    return (
        entry.domains is not None
        or entry.refuse_running
        or entry.refuse_templates
        or entry.refuse_unused
    )


def has_dependents(storage, include_deleted=False):
    """Whether any disk row backs onto ``storage``; ``include_deleted`` counts deleted ones too."""
    if not include_deleted:
        return bool(storage.children)
    return bool(storage.get_children([storage.id], include_deleted=True))


def status_refusal(action, storage_id, status):
    """The ``(description_code, message)`` for a disk in a status ``action`` refuses."""
    code = spec(action).status_refusal
    return code, _STATUS_MESSAGES[code].format(id=storage_id, status=status)


def refusal(
    action,
    *,
    status,
    domains=(),
    has_children=None,
    perms=None,
    storage_id="",
):
    """The ``(description_code, message)`` that refuses ``action``, or None."""
    entry = spec(action)
    domains = list(domains)
    if entry.statuses is not None and status not in entry.statuses:
        return status_refusal(action, storage_id, status)
    if entry.refuse_read_only and perms is not None and "w" not in perms:
        return (
            "storage_read_only",
            f"Storage {storage_id} is read-only (perms without 'w'); it is never written",
        )
    if entry.refuse_unused and not domains:
        return (
            "storage_not_used_by_any_domain",
            f"Storage {storage_id} is not used by any desktop; only a desktop's own disk is written",
        )
    if entry.refuse_templates and any(kind == "template" for kind, _ in domains):
        return (
            "storage_used_by_template",
            f"Storage {storage_id} is a template's disk; a template's disk is never written",
        )
    if entry.refuse_running and any(s in RUNNING for _, s in domains):
        return (
            entry.running_refusal,
            _RUNNING_MESSAGES[entry.running_refusal].format(id=storage_id),
        )
    if entry.domains is not None and any(s not in entry.domains for _, s in domains):
        return (
            "desktops_not_stopped",
            f"Storage {storage_id} must have all domains stopped in order to set it to maintenance. Some desktops are not stopped.",
        )
    if entry.children_block and has_children is not None and has_children():
        return (
            "storage_has_children",
            f"Storage {storage_id} has children storages that depend on it as backing file",
        )
    return None


def allowed_actions(
    *, status, domains=(), has_children=False, has_deleted_children=False, perms=None
):
    """Every registered action the guard would admit on a disk with these facts."""

    def children(action):
        return lambda: has_children or (
            has_deleted_children and spec(action).children_include_deleted
        )

    return sorted(
        action
        for action in DISK_ACTIONS
        if refusal(
            action,
            status=status,
            domains=domains,
            has_children=children(action),
            perms=perms,
        )
        is None
    )
