#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``update_document_if`` / ``delete_document_if`` carry their test to the server.

A settle-path handler that reads a row, decides, and then writes overwrites
whatever changed the row in between. These two put the decision inside the
write, so there is no in between.

The guard is exercised by evaluating the predicate the query carries, not by
asserting the shape of the ReQL: ``r`` is replaced with a tiny evaluator so the
lambda handed to ``update`` / ``replace`` can be called against a row and asked
what it decides.
"""

from unittest.mock import MagicMock

import pytest


class _Value:
    def __init__(self, value, present=True):
        self._value = value
        self._present = present

    def default(self, fallback):
        return self._value if self._present else fallback


class _Row:
    """A row that answers ``row[field].default(...)`` the way ReQL does."""

    def __init__(self, doc):
        self._doc = doc

    def __getitem__(self, field):
        return _Value(self._doc.get(field), present=field in self._doc)


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.connections import rethink_base as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Doc(mod.RethinkBase):
        _rdb_table = "storage"
        _rdb_connection = MagicMock(name="conn")

    monkeypatch.setattr(Doc, "_rdb_context", classmethod(lambda cls: _Ctx()))
    table = MagicMock(name="table-storage")
    monkeypatch.setattr(mod.r, "table", MagicMock(return_value=table))
    monkeypatch.setattr(
        mod.r, "expr", lambda seq: MagicMock(contains=lambda value: value in seq)
    )
    monkeypatch.setattr(
        mod.r,
        "branch",
        lambda condition, when_true, when_false: (
            when_true if condition else when_false
        ),
    )
    return {"Cls": Doc, "table": table}


def _update_predicate(stub):
    stub["table"].get.return_value.update.return_value.run.return_value = {
        "replaced": 1
    }
    return stub["table"].get.return_value.update.call_args.args[0]


def _replace_predicate(stub):
    stub["table"].get.return_value.replace.return_value.run.return_value = {
        "deleted": 1
    }
    return stub["table"].get.return_value.replace.call_args.args[0]


class TestUpdateDocumentIf:
    def test_it_updates_a_row_whose_field_is_still_admitted(self, stub_rdb):
        stub_rdb["table"].get.return_value.update.return_value.run.return_value = {
            "replaced": 1
        }
        applied = stub_rdb["Cls"].update_document_if(
            "s1", {"other": 1}, field="status", values=("deleted",), validate=False
        )
        assert applied is True
        predicate = _update_predicate(stub_rdb)
        assert predicate(_Row({"status": "deleted"})) == {"other": 1}

    def test_it_writes_nothing_when_the_row_has_moved_on(self, stub_rdb):
        stub_rdb["table"].get.return_value.update.return_value.run.return_value = {
            "replaced": 0,
            "unchanged": 1,
        }
        applied = stub_rdb["Cls"].update_document_if(
            "s1", {"other": 1}, field="status", values=("deleted",), validate=False
        )
        assert applied is False
        predicate = _update_predicate(stub_rdb)
        assert predicate(_Row({"status": "ready"})) == {}

    def test_a_missing_field_is_not_admitted(self, stub_rdb):
        stub_rdb["table"].get.return_value.update.return_value.run.return_value = {
            "replaced": 0
        }
        stub_rdb["Cls"].update_document_if(
            "s1", {"other": 1}, field="status", values=("deleted",), validate=False
        )
        predicate = _update_predicate(stub_rdb)
        assert predicate(_Row({})) == {}

    def test_a_status_write_carries_its_clock(self, stub_rdb):
        stub_rdb["table"].get.return_value.update.return_value.run.return_value = {
            "replaced": 1
        }
        stub_rdb["Cls"].update_document_if(
            "s1",
            {"status": "ready"},
            field="status",
            values=("maintenance",),
            validate=False,
        )
        predicate = _update_predicate(stub_rdb)
        written = predicate(_Row({"status": "maintenance"}))
        assert written["status"] == "ready"
        assert isinstance(written.get("status_time"), float)

    def test_an_explicit_clock_is_not_overwritten(self, stub_rdb):
        stub_rdb["table"].get.return_value.update.return_value.run.return_value = {
            "replaced": 1
        }
        stub_rdb["Cls"].update_document_if(
            "s1",
            {"status": "ready", "status_time": 1.0},
            field="status",
            values=("maintenance",),
            validate=False,
        )
        predicate = _update_predicate(stub_rdb)
        assert predicate(_Row({"status": "maintenance"}))["status_time"] == 1.0


class TestDeleteDocumentIf:
    def test_it_deletes_a_row_whose_field_is_still_admitted(self, stub_rdb):
        stub_rdb["table"].get.return_value.replace.return_value.run.return_value = {
            "deleted": 1
        }
        assert (
            stub_rdb["Cls"].delete_document_if(
                "s1", field="status", values=("deleted",)
            )
            is True
        )
        predicate = _replace_predicate(stub_rdb)
        assert predicate(_Row({"status": "deleted"})) is None

    def test_a_row_that_came_back_is_kept(self, stub_rdb):
        stub_rdb["table"].get.return_value.replace.return_value.run.return_value = {
            "deleted": 0
        }
        assert (
            stub_rdb["Cls"].delete_document_if(
                "s1", field="status", values=("deleted",)
            )
            is False
        )
        predicate = _replace_predicate(stub_rdb)
        row = _Row({"status": "ready"})
        assert predicate(row) is row

    def test_a_row_that_is_gone_is_kept(self, stub_rdb):
        stub_rdb["table"].get.return_value.replace.return_value.run.return_value = {
            "deleted": 0
        }
        stub_rdb["Cls"].delete_document_if("s1", field="status", values=("deleted",))
        predicate = _replace_predicate(stub_rdb)
        row = _Row({})
        assert predicate(row) is row
