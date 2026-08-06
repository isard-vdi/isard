#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin ``Helpers.get_old_deleted_entry_ids`` indexed-range parity.

The apiv4 service ``delete_old_entries`` regressed from an indexed
``between(["deleted", r.minval], ["deleted", cutoff], index=
"status_accessed").pluck("id")`` (apiv3
``main:api/src/api/libv2/recycle_bin.py:779``) to a full-table pull
plus Python filter. Re-port the helper and pin the indexed contract
so a future refactor that drops the index back to a Python loop fails
this test.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def helper_module(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Helpers),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    captured = {}

    def fake_table(name):
        table = MagicMock(name="table-" + name)
        captured["table_name"] = name

        def fake_between(lo, hi, index=None):
            captured["between_low"] = lo
            captured["between_high"] = hi
            captured["between_index"] = index
            return table

        table.between = fake_between

        # ``.pluck("id")["id"]`` and ``.run(...)``.
        def fake_pluck(field):
            captured["pluck"] = field
            inner = MagicMock(name="pluck-result")
            # ``[field]`` returns a chain whose ``.run()`` we control.
            getitem = MagicMock(name="getitem")
            getitem.run = MagicMock(return_value=["rb-old-1", "rb-old-2"])
            inner.__getitem__ = lambda self, key: getitem
            return inner

        table.pluck = fake_pluck
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    monkeypatch.setattr(mod.r, "minval", "MINVAL")

    yield mod, captured


class TestGetOldDeletedEntryIds:
    def test_uses_status_accessed_index_range(self, helper_module, monkeypatch):
        mod, captured = helper_module

        # Stub the ``get_old_entries_config`` cached helper so we don't
        # hit the real rdb chain.
        monkeypatch.setattr(
            mod.Helpers,
            "get_old_entries_config",
            classmethod(lambda cls: {"max_time": 24, "action": "delete"}),
        )

        ids = mod.Helpers.get_old_deleted_entry_ids()
        assert ids == ["rb-old-1", "rb-old-2"]
        assert captured["table_name"] == "recycle_bin"
        assert captured["between_index"] == "status_accessed"
        # Lower bound: ["deleted", r.minval]; upper bound:
        # ["deleted", <cutoff timestamp>] — exactly the apiv3 shape.
        assert captured["between_low"][0] == "deleted"
        assert captured["between_low"][1] == "MINVAL"
        assert captured["between_high"][0] == "deleted"
        assert isinstance(captured["between_high"][1], float)
        assert captured["pluck"] == "id"

    def test_returns_empty_when_max_time_unset(self, helper_module, monkeypatch):
        mod, _ = helper_module
        monkeypatch.setattr(
            mod.Helpers,
            "get_old_entries_config",
            classmethod(lambda cls: {"max_time": None, "action": None}),
        )
        # Must NOT touch rdb when no cutoff is configured.
        captured_calls = []
        monkeypatch.setattr(
            mod.r,
            "table",
            lambda name: captured_calls.append(name) or MagicMock(),
        )
        assert mod.Helpers.get_old_deleted_entry_ids() == []
        assert captured_calls == []


@pytest.fixture
def delete_module(monkeypatch):
    """Stub the rdb chain behind ``RecycleBin.delete_old_entries``."""
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    runs = []

    def fake_table(name):
        table = MagicMock(name="table-" + name)

        def fake_get_all(args):
            chain = MagicMock(name="get_all")

            def fake_delete():
                deleted = MagicMock(name="delete")

                def fake_run(conn, array_limit=None):
                    runs.append({"ids": list(args), "array_limit": array_limit})
                    return {"deleted": len(args)}

                deleted.run = fake_run
                return deleted

            chain.delete = fake_delete
            return chain

        table.get_all = fake_get_all
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    monkeypatch.setattr(mod.r, "args", lambda ids: list(ids))

    sleeps = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

    yield mod, runs, sleeps


class TestDeleteOldEntries:
    """Pin the chunked purge.

    A single ``get_all(r.args(...))`` over ``array_limit`` raises
    ReqlResourceLimitError and aborts the whole purge without deleting
    anything, so the backlog grows and every later run fails the same way.
    """

    def test_splits_into_chunks_and_paces_between_them(self, delete_module):
        mod, runs, sleeps = delete_module
        ids = [f"rb-{i}" for i in range(1200)]

        mod.RecycleBin.delete_old_entries(ids, chunk_size=500)

        assert [len(run["ids"]) for run in runs] == [500, 500, 200]
        # Every id is deleted exactly once, order preserved.
        assert [i for run in runs for i in run["ids"]] == ids
        # Paced between chunks, never after the last one.
        assert sleeps == [0.5, 0.5]

    def test_array_limit_stays_under_the_rethinkdb_ceiling(self, delete_module):
        mod, runs, _ = delete_module

        mod.RecycleBin.delete_old_entries([f"rb-{i}" for i in range(10)])

        assert runs and all(run["array_limit"] == 200000 for run in runs)

    def test_single_chunk_does_not_sleep(self, delete_module):
        mod, runs, sleeps = delete_module

        mod.RecycleBin.delete_old_entries(["rb-1", "rb-2"])

        assert len(runs) == 1
        assert sleeps == []

    def test_empty_list_never_touches_rdb(self, delete_module):
        mod, runs, sleeps = delete_module

        mod.RecycleBin.delete_old_entries([])

        assert runs == []
        assert sleeps == []

    def test_accepts_a_non_list_sequence(self, delete_module):
        mod, runs, _ = delete_module

        mod.RecycleBin.delete_old_entries(iter(["rb-1", "rb-2"]), chunk_size=1)

        assert [run["ids"] for run in runs] == [["rb-1"], ["rb-2"]]
