# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for seeding the nightly storage_reconcile job once, keyed by action."""

import ast
from contextlib import nullcontext
from pathlib import Path

_SCHEDULER_PY = (
    Path(__file__).resolve().parents[1] / "src" / "scheduler" / "lib" / "scheduler.py"
)
_SRC = _SCHEDULER_PY.read_text()
_TREE = ast.parse(_SRC)


def _find_function(name):
    for node in ast.walk(_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in scheduler.py")


class _Query:
    """In-memory r.table(...).filter(dict).count().run(conn) over a job list."""

    def __init__(self, rows):
        self._rows = rows

    def filter(self, predicate):
        return _Query(
            [
                row
                for row in self._rows
                if all(row.get(k) == v for k, v in predicate.items())
            ]
        )

    def count(self):
        return _Count(len(self._rows))


class _Count:
    def __init__(self, n):
        self._n = n

    def run(self, conn):
        return self._n


class _FakeR:
    def __init__(self, jobs):
        self._jobs = jobs

    def table(self, name):
        assert name == "scheduler_jobs"
        return _Query(list(self._jobs))


class _FakeApp:
    def app_context(self):
        return nullcontext()


class _FakeDB:
    conn = object()


class _RecordingScheduler:
    """Stands in for ``self``: records every ``add_job`` call."""

    def __init__(self):
        self.calls = []

    def add_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def _seed_with(jobs):
    """Exec only _seed_default_reconcile_job against a fake table; return add_job calls."""
    namespace = {"app": _FakeApp(), "r": _FakeR(jobs), "db": _FakeDB()}
    exec(
        compile(
            ast.Module(
                body=[_find_function("_seed_default_reconcile_job")], type_ignores=[]
            ),
            str(_SCHEDULER_PY),
            "exec",
        ),
        namespace,
    )
    scheduler = _RecordingScheduler()
    namespace["_seed_default_reconcile_job"](scheduler)
    return scheduler.calls


def test_seeds_the_default_job_once_when_the_action_has_none():
    calls = _seed_with([])
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("system", "cron", "storage_reconcile", "3", "0")
    assert kwargs == {"id": "system.storage_reconcile"}


def test_not_duplicated_when_the_system_job_already_exists():
    calls = _seed_with(
        [{"id": "system.storage_reconcile", "action": "storage_reconcile"}]
    )
    assert calls == []


def test_admin_job_for_the_action_is_kept_not_reseeded():
    # An admin rescheduled the reconcile under THEIR own job id. Because the
    # decision counts by action, that row is seen and nothing is seeded on top.
    calls = _seed_with(
        [{"id": "admin.my-nightly-reconcile", "action": "storage_reconcile"}]
    )
    assert calls == []


def test_unrelated_jobs_do_not_block_seeding():
    calls = _seed_with(
        [
            {"id": "system.storage_migration_tick", "action": "storage_migration_tick"},
            {
                "id": "system.delete_expired",
                "action": "delete_expired_notifications_data",
            },
        ]
    )
    assert len(calls) == 1
    assert calls[0][0] == ("system", "cron", "storage_reconcile", "3", "0")
