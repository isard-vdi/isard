#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The red line: no automatic action may rewrite the qcow2 of a disk that
has descendants -- a template whose children back onto it. A child reads its
parent's clusters through the ``backing_file=`` link, so rewriting the parent in
place (sparsify, repair, convert, ...) can corrupt every disk below it.

The single choke point that enforces this at the model layer is
``set_maintenance``: for every action except a fresh-disk ``create``/``download``
it refuses a disk with children (``storage_has_children``). So the contract is:
every ``Storage`` method that WRITES to the file (``DISK_EFFECTS`` != NONE) must
route through that lock, or be an explicitly declared exemption.

Like ``test_disk_effects_contract``, this reads the source rather than the
runtime: the point is to fail when a NEW file-writing action is written without
the guard -- a new action is a new ``def``. (The one place that legitimately
moves a disk WITHOUT this lock is a migration moving a parent whose children
rebase afterwards; that path is a relocation, not an in-place rewrite, and its
own red-line guard against repairing a parent lives in migration_run.py, covered
by test_migration_damaged_source.py.)
"""

import ast
import re
from pathlib import Path

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as _storage
from isardvdi_common.models.storage import DISK_EFFECTS, DiskEffect, Storage

_SOURCE = Path(_storage.__file__)

#: set_maintenance("create"/"download") deliberately SKIP the children guard: the
#: disk being wired in is brand new and by construction has no children yet.
_FRESH_DISK_ACTIONS = {"create", "download"}

#: File-writing methods that legitimately never lock the disk, with the reason.
#: An entry here is a conscious exemption the reviewer signed off on, not a gap.
_NO_LOCK_EXEMPT = {
    # Aborts in-flight tasks after a cancel; it leaves nothing NEW on the parent
    # (what is on disk after an abort is unknown, hence its CHAIN effect), and
    # blocking a cancel on the child guard would wedge the disk it is rescuing.
    "abort_operations": "cancel/cleanup, not an in-place rewrite",
}

_SET_MAINTENANCE = re.compile(r"""set_maintenance\(\s*["']([a-z_]+)["']""")


def _storage_class():
    tree = ast.parse(_SOURCE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Storage":
            return node
    raise AssertionError("class Storage not found in models/storage.py")


def _task_creating_methods():
    """Methods of ``Storage`` whose body calls ``create_task`` -> {name: source}."""
    text = _SOURCE.read_text()
    found = {}
    for node in _storage_class().body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "create_task":
            continue
        body = ast.dump(node)
        if "'create_task'" in body or '"create_task"' in body:
            found[node.name] = ast.get_source_segment(text, node) or ""
    return found


ACTIONS = _task_creating_methods()
_WRITES_FILE = sorted(a for a, e in DISK_EFFECTS.items() if e is not DiskEffect.NONE)


def _maintenance_actions(src):
    return set(_SET_MAINTENANCE.findall(src))


def test_the_scan_finds_the_actions_at_all():
    """A guard on the guard: if the parse breaks, everything below passes
    vacuously and the contract silently stops being enforced."""
    assert len(ACTIONS) >= 15, sorted(ACTIONS)
    assert len(_WRITES_FILE) >= 10, _WRITES_FILE


def test_the_exemptions_still_name_real_file_writing_methods():
    """A stale exemption would silently excuse a method that no longer exists,
    hiding the day a real one loses its guard."""
    stale = sorted(set(_NO_LOCK_EXEMPT) - set(_WRITES_FILE))
    assert not stale, f"exemptions name methods that do not write the file: {stale}"


@pytest.mark.parametrize("action", _WRITES_FILE)
def test_a_file_writing_action_routes_through_the_children_guard(action):
    """Every method that changes the file must lock it with ``set_maintenance``
    (which refuses ``storage_has_children``) -- unless it only ever creates a
    fresh disk, or it is an explicitly declared no-lock exemption."""
    src = ACTIONS[action]
    locks = _maintenance_actions(src)

    if action in _NO_LOCK_EXEMPT:
        assert not locks, (
            f"{action} is exempted from the lock ({_NO_LOCK_EXEMPT[action]}) but "
            "now calls set_maintenance -- drop the exemption or the call."
        )
        return

    assert locks, (
        f"{action} is declared {DISK_EFFECTS[action].value} (it writes to the "
        "file) but never calls set_maintenance, so nothing stops it rewriting a "
        "disk that has descendants. Lock it with set_maintenance, or add it to "
        "_NO_LOCK_EXEMPT with a reason."
    )
    # Fine to only create/download (a fresh disk has no children, so the guard is
    # skipped on purpose); anything else must be a guarded action that trips it.
    if locks <= _FRESH_DISK_ACTIONS:
        return
    assert locks - _FRESH_DISK_ACTIONS, action


# --------------------------------------------------------------------------- #
# The lock itself: it must refuse a disk with descendants for the very actions
# the sweep and the manager enqueue, and skip only a fresh-disk create/download.
# --------------------------------------------------------------------------- #


def _bare(monkeypatch, status, domains=(), children=()):
    # RethinkBase.__setattr__ persists every attribute write to RethinkDB, so a
    # set_maintenance that SUCCEEDS (create/download) would try to reach the DB.
    # Keep writes in memory for the test; the raise-path cases never assign.
    monkeypatch.setattr(Storage, "__setattr__", object.__setattr__)
    monkeypatch.setattr(Storage, "domains", property(lambda self: list(domains)))
    monkeypatch.setattr(Storage, "children", property(lambda self: list(children)))
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = "s-1"
    storage.__dict__["status"] = status
    return storage


def _code(excinfo):
    err = excinfo.value
    return getattr(err, "description_code", None) or (
        err.error.get("description_code")
        if isinstance(getattr(err, "error", None), dict)
        else None
    )


@pytest.mark.parametrize("action", ["sparsify", "repair", "convert"])
def test_the_lock_refuses_a_disk_with_descendants(action, monkeypatch):
    storage = _bare(monkeypatch, "ready", children=["child-1"])

    with pytest.raises(Error) as excinfo:
        storage.set_maintenance(action)

    assert _code(excinfo) == "storage_has_children"


@pytest.mark.parametrize("action", ["create", "download"])
def test_a_fresh_disk_creation_is_not_blocked_by_children(action, monkeypatch):
    """The exemption is real: making a new disk must not be refused just because
    some other disk lists this (not-yet-existing) one as a parent."""
    storage = _bare(monkeypatch, "non_existing", children=["child-1"])

    storage.set_maintenance(action)

    assert storage.status == "maintenance"
