# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the bounded ``desktops_not_stopped`` storage-action retry.

``Actions.wait_desktops_to_do_storage_action`` used to catch a
``desktops_not_stopped`` ApiV4Error and silently ``pass``, so a storage action
(move/convert/…) whose desktops never stop retried forever on the recurring job
with zero visibility. The fix bounds it: each deferral bumps a ``stg_attempts``
counter on the ``{storage_id}.stg_action`` job row, logs a warning, and after
``STG_ACTION_MAX_ATTEMPTS`` abandons the action (removes the job) and logs an
error. ``_bump_stg_action_attempts`` returns ``None`` when the job row is gone
so a concurrently-deleted action cannot crash the tick.

``actions.py`` imports the generated apiv4 clients and initialises a live
rdb/app at module import time (see ``conftest.py``), so — exactly like
``test_misfire_grace`` — these tests do NOT import the module. The pure abandon
predicate is extracted from the real source and executed directly, and the
wiring / None-safety are pinned with structural (AST) assertions on the source.
"""

import ast
from pathlib import Path

_ACTIONS_PY = (
    Path(__file__).resolve().parents[1] / "src" / "scheduler" / "lib" / "actions.py"
)
_SRC = _ACTIONS_PY.read_text()
_TREE = ast.parse(_SRC)


def _load_predicate_namespace():
    """Exec ONLY ``STG_ACTION_MAX_ATTEMPTS`` and ``_stg_action_should_abandon``
    from the real source, in isolation — the full module is not importable in
    the dependency-light scheduler test rig. Source order is preserved so the
    constant (a default-arg value on the predicate) is defined first."""
    wanted = {"STG_ACTION_MAX_ATTEMPTS", "_stg_action_should_abandon"}
    picked = []
    for node in _TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            picked.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in wanted for t in node.targets
        ):
            picked.append(node)
    assert picked, "abandon predicate/constant not found in actions.py"
    namespace = {}
    exec(
        compile(ast.Module(body=picked, type_ignores=[]), str(_ACTIONS_PY), "exec"),
        namespace,
    )
    return namespace


def _find_function(name):
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in actions.py")


def _calls_name(node, name):
    """True if the subtree calls ``name``, bare or as an attribute."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == name:
                return True
            if isinstance(func, ast.Attribute) and func.attr == name:
                return True
    return False


def test_stg_action_max_attempts_default_is_60():
    ns = _load_predicate_namespace()
    assert ns["STG_ACTION_MAX_ATTEMPTS"] == 60


def test_should_abandon_boundary():
    ns = _load_predicate_namespace()
    should = ns["_stg_action_should_abandon"]
    cap = ns["STG_ACTION_MAX_ATTEMPTS"]
    # a gone job row (None) must NEVER count as abandon — a concurrently deleted
    # action must not crash nor be treated as over the cap
    assert should(None) is False
    # below the cap keeps retrying
    assert should(0) is False
    assert should(cap - 1) is False
    # at and above the cap abandons
    assert should(cap) is True
    assert should(cap + 5) is True


def test_should_abandon_respects_custom_cap():
    ns = _load_predicate_namespace()
    should = ns["_stg_action_should_abandon"]
    assert should(4, max_attempts=5) is False
    assert should(5, max_attempts=5) is True
    assert should(6, max_attempts=5) is True


def test_desktops_not_stopped_branch_is_bounded_not_silent():
    """The handler must bump the counter, consult the abandon predicate, and
    delete the job on give-up — i.e. it is no longer a bare silent ``pass``."""
    src = ast.get_source_segment(
        _SRC, _find_function("wait_desktops_to_do_storage_action")
    )
    assert "_bump_stg_action_attempts(" in src
    assert "_stg_action_should_abandon(" in src
    assert "scheduler_client.delete(" in src


def test_desktops_not_stopped_delete_is_inside_the_abandon_guard():
    """The delete must sit INSIDE the ``_stg_action_should_abandon`` branch.

    The test above reads the handler as text, so all three calls being present
    somewhere in it satisfies it — including the shape this bound exists to
    prevent, where the delete has drifted out of the guard and the action is
    abandoned on its FIRST deferral instead of on crossing the cap. Containment
    is a structural property, so it is asserted on the tree.
    """
    handler = _find_function("wait_desktops_to_do_storage_action")

    branch = None
    for node in ast.walk(handler):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            if any(
                isinstance(other, ast.Constant)
                and other.value == "desktops_not_stopped"
                for other in node.test.comparators
            ):
                branch = node
    assert branch is not None, "desktops_not_stopped branch not found"

    guard = None
    for node in ast.walk(branch):
        if isinstance(node, ast.If) and _calls_name(
            node.test, "_stg_action_should_abandon"
        ):
            guard = node
    assert guard is not None, "the abandon delete is no longer gated by the cap"
    assert any(
        _calls_name(stmt, "delete") for stmt in guard.body
    ), "the capped branch must be the one that removes the job"


def test_bump_attempts_is_none_safe():
    """``_bump_stg_action_attempts`` must swallow the missing-row parse errors
    and return None so a concurrently-deleted action cannot crash the tick."""
    fn = _find_function("_bump_stg_action_attempts")
    caught = set()
    returns_none = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            exc = handler.type
            if isinstance(exc, ast.Tuple):
                caught.update(e.id for e in exc.elts if isinstance(e, ast.Name))
            elif isinstance(exc, ast.Name):
                caught.add(exc.id)
            for stmt in ast.walk(handler):
                if isinstance(stmt, ast.Return) and (
                    stmt.value is None
                    or (
                        isinstance(stmt.value, ast.Constant)
                        and stmt.value.value is None
                    )
                ):
                    returns_none = True
    assert {"KeyError", "IndexError", "TypeError"} <= caught
    assert returns_none
