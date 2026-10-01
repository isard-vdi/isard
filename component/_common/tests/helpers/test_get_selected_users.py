#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Alloweds.get_selected_users`` resolves the ids in an item's
``allowed.users`` so the alloweds modal can name every selected user,
including ones it never listed."""

import contextlib

import pytest
from isardvdi_common.helpers import alloweds as alloweds_module
from isardvdi_common.helpers.alloweds import Alloweds


class _FakeQuery:
    """Swallows the whole ReQL chain and returns the rows given to it."""

    def __init__(self, rows, calls):
        self._rows = rows
        self._calls = calls

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self._calls.append((name, args))
            return self

        return _record

    def run(self, _conn):
        return self._rows


@pytest.fixture
def rows_from(monkeypatch):
    calls = []

    def _install(rows):
        def _table(name):
            calls.append(("table", (name,)))
            return _FakeQuery(rows, calls)

        monkeypatch.setattr(
            alloweds_module, "r", type("_R", (), {"table": staticmethod(_table)})()
        )
        monkeypatch.setattr(
            Alloweds, "_rdb_context", classmethod(lambda cls: contextlib.nullcontext())
        )
        return calls

    return _install


def test_returns_the_selected_users(rows_from):
    rows = [
        {"id": "u-1", "name": "Anna", "username": "anna", "photo": "", "group": "g-1"},
        {"id": "u-2", "name": "Joan", "username": "joan", "photo": "", "group": "g-2"},
    ]
    calls = rows_from(rows)

    assert Alloweds.get_selected_users(["u-1", "u-2"]) == rows
    assert ("table", ("users",)) in calls
    assert ("get_all", ("u-1", "u-2")) in calls


@pytest.mark.parametrize("allowed_users", [False, True, []])
def test_no_users_selected_skips_the_query(monkeypatch, allowed_users):
    monkeypatch.setattr(alloweds_module, "r", None)

    assert Alloweds.get_selected_users(allowed_users) == []
