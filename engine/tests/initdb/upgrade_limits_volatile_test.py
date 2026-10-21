# SPDX-License-Identifier: AGPL-3.0-or-later

"""v215 adds ``volatile`` to group and category limits stored without it, so the
temporary desktop gate finds the key. Loaded bare from ``upgrade_helpers.py``
like the other pure helpers."""

import ast
import runpy
import types
from unittest.mock import MagicMock

import pytest
from tests.helpers import SRC_ROOT

m = types.SimpleNamespace(
    **runpy.run_path(
        str(SRC_ROOT / "initdb" / "upgrade_helpers.py"),
        run_name="_limits_volatile_under_test",
    )
)


@pytest.mark.parametrize(
    "limits,expected",
    [
        ({"desktops": 10, "vcpus": 4}, True),  # saved from the admin form
        ({"desktops": 10, "volatile": 2}, False),  # already carries it
        ({"desktops": 10, "volatile": 0}, False),  # zero is a real limit
        (False, False),  # no limits set
        (None, False),
        ({}, True),
    ],
)
def test_limits_missing_volatile(limits, expected):
    assert m.limits_missing_volatile(limits) is expected


def test_the_added_limit_is_the_one_release_128_gave_the_quotas():
    assert m.V215_VOLATILE_LIMIT == 999


def _db(monkeypatch, rows, update_results):
    r = MagicMock()
    r.args.side_effect = list
    table = r.table.return_value
    table.pluck.return_value.run.return_value = rows
    table.get_all.return_value.update.return_value.run.side_effect = update_results
    log = MagicMock()
    monkeypatch.setitem(m.v215_limits_volatile.__globals__, "r", r)
    monkeypatch.setitem(m.v215_limits_volatile.__globals__, "log", log)
    return table, log


def test_only_limits_without_volatile_are_updated(monkeypatch):
    rows = [
        {"id": "a", "limits": {"desktops": 10}},
        {"id": "b", "limits": {"desktops": 10, "volatile": 2}},
        {"id": "c", "limits": False},
        {"id": "d"},
        {"id": "e", "limits": {}},
    ]
    table, log = _db(monkeypatch, rows, [None])

    m.v215_limits_volatile(types.SimpleNamespace(conn="conn"), "groups")

    table.get_all.assert_called_once_with(["a", "e"])
    table.get_all.return_value.update.assert_called_once_with(
        {"limits": {"volatile": 999}}
    )
    log.error.assert_not_called()


def test_a_failing_batch_is_logged_and_the_next_one_still_runs(monkeypatch):
    rows = [{"id": f"g{i}", "limits": {"desktops": 1}} for i in range(600)]
    table, log = _db(monkeypatch, rows, [RuntimeError("write failed"), None])

    m.v215_limits_volatile(types.SimpleNamespace(conn="conn"), "categories")

    assert table.get_all.call_count == 2
    log.error.assert_called_once()
    assert "categories" in log.error.call_args.args[0]
    assert "write failed" in log.error.call_args.args[0]
    assert "100 of 600" in log.info.call_args.args[0]


def test_every_v215_call_in_the_upgrade_is_guarded():
    tree = ast.parse((SRC_ROOT / "initdb" / "upgrade.py").read_text())
    guarded = {
        id(node)
        for t in ast.walk(tree)
        if isinstance(t, ast.Try) and t.handlers
        for stmt in t.body
        for node in ast.walk(stmt)
    }
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "v215_limits_volatile"
    ]
    assert len(calls) == 2
    assert all(id(c) in guarded for c in calls)
