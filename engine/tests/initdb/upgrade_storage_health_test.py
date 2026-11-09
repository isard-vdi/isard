# SPDX-License-Identifier: AGPL-3.0-or-later

"""v216 creates only the storage indexes that are missing, survives a failing
index or batch, and backfills the integrity check time."""

import ast
import runpy
import types

from tests.helpers import SRC_ROOT

m = types.SimpleNamespace(
    **runpy.run_path(
        str(SRC_ROOT / "initdb" / "upgrade_helpers.py"),
        run_name="_storage_health_under_test",
    )
)


class _Run:
    def __init__(self, value=None, error=None, calls=None, name=None):
        self.value, self.error, self.calls, self.name = value, error, calls, name

    def run(self, conn):
        if self.calls is not None:
            self.calls.append(self.name)
        if self.error:
            raise self.error
        return self.value


class FakeTable:
    def __init__(self, existing=(), failing=(), list_error=None):
        self.existing, self.failing, self.list_error = (
            list(existing),
            failing,
            list_error,
        )
        self.calls = []

    def index_list(self):
        return _Run(self.existing, self.list_error)

    def index_create(self, name, function, multi=False):
        return _Run(
            error=RuntimeError("boom") if name in self.failing else None,
            calls=self.calls,
            name=(name, multi),
        )

    def index_wait(self):
        return _Run(calls=self.calls, name="wait")


INDEXES = {"a": (None, False), "b": (None, True), "c": (None, False)}


def test_only_the_missing_indexes_are_created_and_waited_for_once():
    table, warnings = FakeTable(existing=["a"]), []
    created = m.v216_create_indexes(table, None, INDEXES, warnings.append)
    assert created == ["b", "c"]
    assert table.calls == [("b", True), ("c", False), "wait"]
    assert warnings == []


def test_a_second_run_creates_nothing():
    table = FakeTable(existing=list(INDEXES))
    assert m.v216_create_indexes(table, None, INDEXES, print) == []
    assert table.calls == ["wait"]


def test_one_failing_index_does_not_stop_the_others():
    table, warnings = FakeTable(failing={"a"}), []
    created = m.v216_create_indexes(table, None, INDEXES, warnings.append)
    assert created == ["b", "c"]
    assert len(warnings) == 1 and "v216" in warnings[0] and "a" in warnings[0]


def test_an_unreadable_index_list_still_creates_them():
    table, warnings = FakeTable(list_error=RuntimeError("down")), []
    assert m.v216_create_indexes(table, None, INDEXES, warnings.append) == list(INDEXES)
    assert len(warnings) == 1


def test_a_failing_batch_is_logged_and_the_next_one_still_runs():
    seen, warnings = [], []

    def update(batch):
        seen.append(batch)
        if batch[0] == 3:
            raise RuntimeError("timeout")
        return len(batch)

    done, failed = m.v216_backfill_integrity_at(
        list(range(7)), update, warnings.append, batch_size=3
    )
    assert seen == [[0, 1, 2], [3, 4, 5], [6]]
    assert (done, failed) == (4, 3)
    assert len(warnings) == 1 and "v216" in warnings[0]


class _Query:
    def __init__(self, result):
        self.result, self.ids = result, None

    def get_all(self, *ids):
        self.ids = ids
        return self

    def filter(self, _):
        return self

    def update(self, _):
        return self

    def run(self, conn):
        return self.result


def test_a_batch_counts_the_rows_it_replaced():
    table = _Query({"replaced": 2, "unchanged": 1})
    assert m.v216_backfill_batch(table, None, ["a", "b", "c"]) == 2
    assert table.ids == ("a", "b", "c")


def test_a_batch_with_row_errors_fails_instead_of_passing_short():
    table = _Query({"replaced": 1, "errors": 2, "first_error": "No attribute"})
    try:
        m.v216_backfill_batch(table, None, ["a", "b", "c"])
    except RuntimeError as e:
        assert "2 rows failed" in str(e) and "No attribute" in str(e)
    else:
        raise AssertionError("a batch with row errors passed")


def test_the_indexes_are_the_three_the_sweep_reads():
    names = set(m.v216_storage_indexes(None, 1))
    assert names == {
        "status_integrity_checked",
        "status_zeros_due",
        "status_pending_action_since",
    }
    assert m.v216_storage_indexes(None, 1)["status_pending_action_since"][1] is True


def test_the_runner_reaches_release_216_through_the_storage_table():
    source = (SRC_ROOT / "initdb" / "upgrade.py").read_text()
    tree = ast.parse(source)
    release = next(
        n.value.value
        for n in tree.body
        if isinstance(n, ast.Assign)
        and getattr(n.targets[0], "id", None) == "release_version"
    )
    assert release == 216
    assert "if version == 216:" in source and "v216_storage_health(self)" in source
