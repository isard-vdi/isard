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
