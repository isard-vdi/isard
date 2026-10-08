# SPDX-License-Identifier: AGPL-3.0-or-later

"""The operator tools in ``utils/`` reach the database through apiv4, never directly."""

import ast
from pathlib import Path

UTILS = Path(__file__).resolve().parents[1] / "utils"

#: Direct database access that predates this guard: shrink it, never grow it.
LEGACY = {
    ("analyze", "<module>", "rethinkdb"),
    ("check_chains", "<module>", "rethinkdb"),
    ("storage", "cmd_db_cleanup", "storage_lib.db"),
    ("storage", "cmd_migrate_default_pool", "storage_lib.db"),
    ("storage_lib/db.py", "<module>", "rethinkdb"),
}


def _is_database(module):
    return (
        module == "rethinkdb"
        or module.startswith("rethinkdb.")
        or module in ("storage_lib.db", "db")
        or module.startswith("isardvdi_common.models")
        or module.startswith("isardvdi_common.connections.rethink")
    )


def _python_tools():
    for path in sorted(UTILS.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        source = path.read_text(errors="replace")
        first_line = source.split("\n", 1)[0]
        if path.suffix == ".py" or (
            first_line.startswith("#!") and "python" in first_line
        ):
            yield path, source


def _database_imports(source, name):
    found = set()

    def walk(node, function):
        for child in ast.iter_child_nodes(node):
            inner = function
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = child.name
            if isinstance(child, ast.Import):
                modules = [alias.name for alias in child.names]
            elif isinstance(child, ast.ImportFrom):
                modules = [child.module or ""]
            else:
                modules = []
            for module in modules:
                if _is_database(module):
                    found.add((name, function or "<module>", module))
            walk(child, inner)

    walk(ast.parse(source), None)
    return found


def _all_database_imports():
    found = set()
    for path, source in _python_tools():
        found |= _database_imports(source, path.relative_to(UTILS).as_posix())
    return found


def test_no_tool_opens_a_new_path_to_the_database():
    new = _all_database_imports() - LEGACY
    assert not new, (
        "isard-storage runs on nodes with no database; read and write through "
        f"storage_lib.api instead: {sorted(new)}"
    )


def test_the_legacy_list_only_names_what_still_exists():
    gone = LEGACY - _all_database_imports()
    assert not gone, f"already moved to the API, drop them from LEGACY: {sorted(gone)}"


def test_the_detector_sees_an_import_inside_a_function():
    source = "def cmd_x(args):\n    from storage_lib.db import get_conn\n"
    assert _database_imports(source, "tool") == {("tool", "cmd_x", "storage_lib.db")}
