#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-group user counts (primary and secondary members) for the alloweds modal's group subtitles.

The counts change with every user edit while the group list is cached, so
they must be merged into copies and never written into the cached rows."""

import contextlib

import pytest
from isardvdi_common.helpers import alloweds as alloweds_module
from isardvdi_common.helpers.alloweds import Alloweds


class _FakeQuery:
    """Swallows the whole ReQL chain and returns the result given to it."""

    def __init__(self, result, calls):
        self._result = result
        self._calls = calls

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self._calls.append((name, args))
            return self

        return _record

    def run(self, _conn):
        return self._result


@pytest.fixture
def query_returns(monkeypatch):
    calls = []

    def _install(result):
        def _table(name):
            calls.append(("table", (name,)))
            return _FakeQuery(result, calls)

        monkeypatch.setattr(
            alloweds_module, "r", type("_R", (), {"table": staticmethod(_table)})()
        )
        monkeypatch.setattr(
            Alloweds, "_rdb_context", classmethod(lambda cls: contextlib.nullcontext())
        )
        return calls

    return _install


def test_counts_users_by_primary_and_secondary_group(query_returns):
    calls = query_returns({"g-1": 3, "g-2": 1})

    assert Alloweds.get_users_count_by_group("cat-1") == {"g-1": 3, "g-2": 1}
    assert ("table", ("users",)) in calls
    assert any(name == "concat_map" for name, _ in calls)


def test_merges_counts_into_copies_of_the_cached_groups(monkeypatch):
    cached = [{"id": "g-1", "name": "One"}, {"id": "g-2", "name": "Two"}]
    monkeypatch.setattr(
        Alloweds, "get_allowed_groups", classmethod(lambda cls, category_id: cached)
    )
    monkeypatch.setattr(
        Alloweds,
        "get_users_count_by_group",
        classmethod(lambda cls, category_id: {"g-1": 5}),
    )

    groups = Alloweds.get_allowed_groups_with_users_count("cat-1")

    assert groups == [
        {"id": "g-1", "name": "One", "users_count": 5},
        {"id": "g-2", "name": "Two", "users_count": 0},
    ]
    assert all("users_count" not in group for group in cached)
