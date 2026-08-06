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
"""An action that starts a task must hand its caller the task.

Written as a scan over the class rather than a list of method names: a list
cannot fail for a method nobody added to it, which is how ``convert`` sat for
months promising ``:return: Task ID`` in its docstring and returning ``None``,
with its caller in apiv4 answering ``"task_id": null`` to a conversion it had
just started.
"""

import ast
import inspect

import pytest
from isardvdi_common.models import storage as storage_module
from isardvdi_common.models.storage import Storage

# ``create_task`` is the factory itself: it writes ``self.task`` and every other
# method reads it back, so it is the one member of the family with nothing to
# return.
_FACTORY = "create_task"


def _task_creating_methods():
    tree = ast.parse(inspect.getsource(storage_module))
    klass = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == Storage.__name__
    )
    found = {}
    for node in klass.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == _FACTORY:
            continue
        body = ast.get_source_segment(inspect.getsource(storage_module), node) or ""
        if "create_task(" in body:
            found[node.name] = node
    return found


ACTIONS = _task_creating_methods()


def test_the_scan_finds_the_family_it_is_meant_to_guard():
    """A refactor that renames ``create_task`` would empty the scan and leave
    every assertion below vacuously true."""
    assert len(ACTIONS) >= 15


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_a_task_creating_action_returns_its_task(name):
    returns = [
        node
        for node in ast.walk(ACTIONS[name])
        if isinstance(node, ast.Return) and node.value is not None
    ]
    assert returns, (
        f"Storage.{name}() starts a task and returns nothing, so its caller "
        "cannot poll or cancel the work it just requested"
    )
