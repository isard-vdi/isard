#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A force delete must never drop the desktop row while its disks are still
owned by it.

Read as source rather than executed: importing the controller pulls in libvirt
and the whole engine object graph, which this suite has no way to stand up. The
two properties below are structural, so the text is enough to hold them.
"""

import ast
import pathlib

SOURCE = pathlib.Path(__file__).with_name("ui_actions.py").read_text()
TREE = ast.parse(SOURCE)


def _function(name):
    return next(
        node
        for node in ast.walk(TREE)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_enqueuing_the_disk_deletion_reports_whether_it_worked():
    """The swallowed exception used to fall through to ``return True``."""
    body = ast.get_source_segment(SOURCE, _function("deleting_disks_from_domain"))
    assert "failed = True" in body, "the enqueue failure is not recorded"
    assert "return not failed" in body, "the outcome is not reported to the caller"


def test_the_row_is_only_dropped_once_the_disks_are_enqueued():
    """``delete_domain`` must sit behind the enqueue result, not beside it."""
    force_deleting = _function("force_deleting")
    body = ast.get_source_segment(SOURCE, force_deleting)
    assert "if not self.deleting_disks_from_domain(" in body

    guard = next(
        node
        for node in force_deleting.body
        if isinstance(node, ast.If)
        and "deleting_disks_from_domain" in (ast.get_source_segment(SOURCE, node) or "")
    )
    assert any(
        isinstance(node, ast.Return) for node in guard.body
    ), "the guard falls through instead of returning"

    guard_index = force_deleting.body.index(guard)
    deletes = [
        index
        for index, node in enumerate(force_deleting.body)
        if "delete_domain(" in (ast.get_source_segment(SOURCE, node) or "")
        and index != guard_index
    ]
    assert deletes, "force_deleting no longer deletes the row at all"
    assert min(deletes) > guard_index, "the row is dropped before the guard runs"


def test_the_precondition_excludes_the_desktop_being_deleted():
    """Its own status is never Stopped on this path: the engine stops it with
    ``not_change_status``, so requiring it would refuse every time."""
    body = ast.get_source_segment(SOURCE, _function("deleting_disks_from_domain"))
    assert "exclude_domains=[id_domain]" in body
