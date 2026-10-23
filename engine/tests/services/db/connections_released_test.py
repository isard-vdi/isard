# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every pooled RethinkDB connection the engine takes is released, even when the query raises."""

import ast

import pytest
from tests.helpers import ENGINE_SRC


def _sources():
    return sorted(
        p
        for p in ENGINE_SRC.rglob("*.py")
        if not p.name.endswith("_test.py") and not p.name.startswith("test_")
    )


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _releases(stmts, name):
    for stmt in stmts:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and _call_name(node) == "close_rethink_connection"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == name
            ):
                return True
    return False


def _guarded(block, index):
    stmt = block[index]
    if not (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and isinstance(stmt.value, ast.Call)
        and _call_name(stmt.value) == "new_rethink_connection"
    ):
        return False
    following = block[index + 1] if index + 1 < len(block) else None
    return isinstance(following, ast.Try) and _releases(
        following.finalbody, stmt.targets[0].id
    )


def _unreleased(path, root=ENGINE_SRC):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded = set()
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block):
                if _guarded(block, i):
                    guarded.add(id(stmt.value))
    rel = path.relative_to(root)
    return [
        f"{rel}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _call_name(node) == "new_rethink_connection"
        and id(node) not in guarded
    ]


def test_the_scan_covers_the_engine_sources():
    assert any(p.name == "domains.py" for p in _sources())


def test_the_scan_flags_an_unguarded_acquire(tmp_path):
    (tmp_path / "leaky.py").write_text(
        "def f():\n"
        "    c = new_rethink_connection()\n"
        "    out = q.run(c)\n"
        "    close_rethink_connection(c)\n"
        "    return out\n"
        "\n"
        "def g():\n"
        "    c = new_rethink_connection()\n"
        "    try:\n"
        "        return q.run(c)\n"
        "    finally:\n"
        "        close_rethink_connection(c)\n"
    )
    assert _unreleased(tmp_path / "leaky.py", tmp_path) == ["leaky.py:2"]


@pytest.mark.parametrize(
    "path", _sources(), ids=lambda p: str(p.relative_to(ENGINE_SRC))
)
def test_every_acquire_is_released_on_error(path):
    """A raising query must not keep its pool slot: use rethink_conn() or try/finally."""
    assert _unreleased(path) == []
