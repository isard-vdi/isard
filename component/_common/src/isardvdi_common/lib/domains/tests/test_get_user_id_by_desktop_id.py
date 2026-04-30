#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``DomainsProcessed.get_user_id_by_desktop_id`` (tier 3.4 batch 1).

Migrated from the inline ``r.table("domains").get_all(...).pluck("id", "user")``
block previously living in apiv4's
``services/admin/notify.py:notify_desktop_queue``.

Pins:
* the result is a {desktop_id: user_id} map (not the raw list),
* desktops not found in the DB are absent from the map (the caller
  silently skips them).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.domains import domains as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DomainsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DomainsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    yield {"mock_table": mock_table, "Processed": mod.DomainsProcessed}


class TestGetUserIdByDesktopId:
    def test_returns_map(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "d-1", "user": "u-a"},
            {"id": "d-2", "user": "u-b"},
        ]
        result = stub_rdb["Processed"].get_user_id_by_desktop_id(["d-1", "d-2"])
        assert result == {"d-1": "u-a", "d-2": "u-b"}

    def test_missing_desktops_absent_from_map(self, stub_rdb):
        """If a desktop id wasn't found, it's absent from the result —
        the caller skips notifying that user."""
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "d-1", "user": "u-a"},
        ]
        result = stub_rdb["Processed"].get_user_id_by_desktop_id(["d-1", "missing-id"])
        assert result == {"d-1": "u-a"}
        assert "missing-id" not in result

    def test_empty_input_returns_empty(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = []
        assert stub_rdb["Processed"].get_user_id_by_desktop_id([]) == {}
