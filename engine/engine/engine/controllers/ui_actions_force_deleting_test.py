"""``force_deleting`` must destroy the VM wherever it actually is.

It used to ask the hypervisor to destroy the domain only when ``old_status``
was one of Started/Shutting-down/Stopping/Paused, and then removed the domain
row and its disks regardless. A WaitingIP or Starting desktop was therefore
left running on the hypervisor with its row gone and, once the storage-delete
task started being enqueued at all, its disk pulled from under it.

``ui_actions`` cannot be imported bare (it pulls the engine's DB, libvirt and
rethink stack), so ast-parse it and pin the shape of the function.
"""

import ast
import os

_SRC = os.path.join(os.path.dirname(__file__), "ui_actions.py")


def _force_deleting():
    tree = ast.parse(open(_SRC).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "force_deleting":
            return node
    raise AssertionError("force_deleting not found in ui_actions.py")


def _called_names(node):
    """Call names in source order — ast.walk is breadth-first, so a call
    nested in an ``if`` would otherwise sort after the statements below it."""
    calls = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            calls.append((sub.lineno, name))
    return [name for _, name in sorted(calls)]


def test_destroy_is_not_gated_on_old_status():
    body = ast.unparse(ast.Module(body=_force_deleting().body, type_ignores=[]))

    assert "old_status" not in body


def test_stops_the_domain_before_deleting_its_disks():
    called = _called_names(_force_deleting())

    assert called.index("get_domain_hyp_started") < called.index("stop_domain")
    assert called.index("stop_domain") < called.index("deleting_disks_from_domain")
    assert called.index("deleting_disks_from_domain") < called.index("delete_domain")
