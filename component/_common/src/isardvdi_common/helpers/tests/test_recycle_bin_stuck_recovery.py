#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Helpers.get_stuck_delete_entries`` — the query behind admin recovery.

It selects entries stranded mid-delete (``deleting`` + ``queued``) via the
``status`` index. These are the ones an ``isard-api`` restart can orphan: the
startup reconcile only re-enqueues ``queued``, so a ``deleting`` entry whose
work was lost is never retried until an admin recovers it.
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
        captured["table_name"] = name
        table = MagicMock(name="table-" + name)

        def fake_get_all(*values, index=None):
            captured["get_all_values"] = values
            captured["get_all_index"] = index
            return table

        table.get_all = fake_get_all

        def fake_filter(fn):
            captured["filtered"] = True
            return table

        table.filter = fake_filter

        def fake_merge(fn):
            captured["merged"] = True
            return table

        table.merge = fake_merge

        def fake_pluck(*fields):
            captured["pluck"] = fields
            result = MagicMock(name="pluck-result")
            result.run = MagicMock(return_value=[{"id": "rb-stuck-1"}])
            return result

        table.pluck = fake_pluck
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    yield mod, captured


class TestGetStuckDeleteEntries:
    def test_selects_deleting_and_queued_by_status_index(self, helper_module):
        mod, captured = helper_module
        rows = mod.Helpers.get_stuck_delete_entries()
        assert rows == [{"id": "rb-stuck-1"}]
        assert captured["table_name"] == "recycle_bin"
        assert captured["get_all_index"] == "status"
        assert set(captured["get_all_values"]) == {"deleting", "queued"}
        # No age filter by default.
        assert "filtered" not in captured
        # storages_count is projected (merge) so a list endpoint stays lean.
        assert captured["merged"] is True
        assert "id" in captured["pluck"] and "status" in captured["pluck"]

    def test_age_threshold_applies_filter(self, helper_module):
        mod, captured = helper_module
        mod.Helpers.get_stuck_delete_entries(older_than_minutes=30)
        assert captured.get("filtered") is True
