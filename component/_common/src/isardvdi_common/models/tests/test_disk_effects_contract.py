#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every action that creates a storage task must declare what it does to the file.

The stored ``qemu-img-info`` is a snapshot; nothing watches the filesystem. An
action that changes the file and does not re-measure it leaves the row lying,
and the task still reports success -- so the omission is invisible until a quota
or a cleanup reads the stale value.

``convert`` shipped that way: it writes a flat image and its chain ended at
``update_status``, so the destination reached its final status carrying no
``qemu-img-info`` at all. On a live install that showed up as a template
reporting 0 bytes while holding 432 MB.

These tests read the source rather than the runtime: the point is to fail when a
NEW action is written, and a new action is a new ``def``.
"""

import ast
from pathlib import Path

import pytest
from isardvdi_common.models.storage import DISK_EFFECTS, DiskEffect

_SOURCE = Path(__file__).resolve().parents[1] / "storage.py"
#: The task that re-measures a disk and feeds ``storage_update``.
_REFRESH = "qemu_img_info_backing_chain"


def _storage_class():
    tree = ast.parse(_SOURCE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Storage":
            return node
    raise AssertionError("class Storage not found in models/storage.py")


def _task_creating_methods():
    """Methods of ``Storage`` whose body calls ``create_task``."""
    found = {}
    for node in _storage_class().body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "create_task":
            continue
        body = ast.dump(node)
        if "'create_task'" in body or '"create_task"' in body:
            found[node.name] = ast.get_source_segment(_SOURCE.read_text(), node) or ""
    return found


ACTIONS = _task_creating_methods()


def test_the_scan_finds_the_actions_at_all():
    """A guard on the guard: if the parse breaks, everything below passes
    vacuously and the contract silently stops being enforced."""
    assert len(ACTIONS) >= 15, sorted(ACTIONS)


def test_every_task_creating_action_declares_its_effect():
    undeclared = sorted(set(ACTIONS) - set(DISK_EFFECTS))
    assert not undeclared, (
        "these actions create a storage task but never say what they do to the "
        f"file, so nobody can tell whether the row needs re-measuring: {undeclared}. "
        "Add them to DISK_EFFECTS."
    )


def test_no_stale_declarations():
    """A declaration for a method that no longer exists hides a real gap."""
    gone = sorted(set(DISK_EFFECTS) - set(ACTIONS))
    assert not gone, f"DISK_EFFECTS names methods that no longer create tasks: {gone}"


@pytest.mark.parametrize(
    "action",
    sorted(
        a for a, e in DISK_EFFECTS.items() if e in (DiskEffect.SIZE, DiskEffect.CHAIN)
    ),
)
def test_an_action_that_changes_the_file_re_measures_it(action):
    """SIZE and CHAIN both mean the bytes on disk moved; the row must follow."""
    assert _REFRESH in ACTIONS[action], (
        f"{action} is declared {DISK_EFFECTS[action].value}, so it changes the "
        f"file -- but its chain never runs {_REFRESH}, so the stored "
        "qemu-img-info keeps describing the disk as it was before."
    )


@pytest.mark.parametrize(
    "action", sorted(a for a, e in DISK_EFFECTS.items() if e is DiskEffect.PATH)
)
def test_an_action_that_moves_the_file_updates_the_recorded_path(action):
    assert "directory_path" in ACTIONS[action], (
        f"{action} is declared PATH, so the file lands somewhere new -- but its "
        "chain never writes directory_path, leaving the row pointing at the old "
        "location."
    )


@pytest.mark.parametrize(
    "action", sorted(a for a, e in DISK_EFFECTS.items() if e is DiskEffect.NONE)
)
def test_a_no_op_action_does_not_pay_for_a_refresh(action):
    """NONE means the file is untouched, gone, or being measured right now.

    ``check_backing_chain`` is the measurement itself, so it is the one NONE
    that legitimately carries the refresh task.
    """
    if action == "check_backing_chain":
        assert _REFRESH in ACTIONS[action]
        return
    assert _REFRESH not in ACTIONS[action], (
        f"{action} is declared NONE but enqueues {_REFRESH}: either it does "
        "change the file (fix the declaration) or it is buying a measurement "
        "nobody needs on the maintenance tier."
    )
