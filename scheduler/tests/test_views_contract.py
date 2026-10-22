# SPDX-License-Identifier: AGPL-3.0-or-later

import ast
import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VIEWS = _ROOT / "src" / "scheduler" / "views" / "SchedulerView.py"
_SCHEDULER = _ROOT / "src" / "scheduler" / "lib" / "scheduler.py"
_SPEC = _ROOT.parent / "pkg" / "oas" / "scheduler" / "scheduler.json"


def _scheduler_methods():
    tree = ast.parse(_SCHEDULER.read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Scheduler"
    )
    return {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}


def _called_scheduler_methods():
    calls = set()
    for node in ast.walk(ast.parse(_VIEWS.read_text())):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "scheduler"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "app"
        ):
            calls.add(node.attr)
    return calls


def _view_routes():
    routes = set()
    for node in ast.walk(ast.parse(_VIEWS.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "route"
        ):
            path = node.args[0].value
            methods = next((k.value for k in node.keywords if k.arg == "methods"), None)
            for method in [m.value for m in methods.elts] if methods else ["GET"]:
                routes.add((method, re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", path)))
    return routes


def test_every_view_calls_an_existing_scheduler_method():
    assert _called_scheduler_methods() - _scheduler_methods() == set()


def test_every_documented_route_is_served():
    spec = json.loads(_SPEC.read_text())
    documented = {
        (method.upper(), path) for path, ops in spec["paths"].items() for method in ops
    }
    assert documented - _view_routes() == set()
