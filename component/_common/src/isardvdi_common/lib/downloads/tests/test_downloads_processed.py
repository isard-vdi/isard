#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``DownloadsProcessed`` (tier 3.4 batch 3).

Migrated from the inline ``r.table(kind)`` blocks previously living in
apiv4's ``services/admin/downloads.py``. The service still owns the
catalogue-merge orchestration; these tests pin only the data-access
shapes per kind.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on DownloadsProcessed so the methods
    run without a real rethinkdb."""
    from isardvdi_common.lib.downloads import downloads as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DownloadsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DownloadsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    yield {"mock_table": mock_table, "Processed": mod.DownloadsProcessed}


class TestListUserKindDownloads:
    def test_returns_rows_for_domains(self, stub_rdb):
        rows = [{"id": "d1", "url-isard": "u1"}, {"id": "d2", "url-isard": "u2"}]
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.has_fields.return_value.filter.return_value.run.return_value = (
            rows
        )
        result = stub_rdb["Processed"].list_user_kind_downloads("domains", "user-1")
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("domains")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "user-1", index="user"
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.has_fields.assert_called_with("url-isard")

    def test_works_for_media(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.has_fields.return_value.filter.return_value.run.return_value = (
            []
        )
        result = stub_rdb["Processed"].list_user_kind_downloads("media", "user-1")
        assert result == []
        stub_rdb["mock_table"].assert_any_call("media")


class TestListUserMediaUrlWebDownloads:
    def test_filters_url_web_field(self, stub_rdb):
        rows = [{"id": "m1", "url-web": "http://x"}]
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.has_fields.return_value.filter.return_value.run.return_value = (
            rows
        )
        result = stub_rdb["Processed"].list_user_media_url_web_downloads("user-1")
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("media")
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.has_fields.assert_called_with("url-web")


class TestListTableRows:
    def test_returns_full_table(self, stub_rdb):
        rows = [{"id": "v1"}, {"id": "v2"}]
        stub_rdb["mock_table"].return_value.run.return_value = rows
        result = stub_rdb["Processed"].list_table_rows("virt_install")
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("virt_install")

    def test_works_for_videos(self, stub_rdb):
        stub_rdb["mock_table"].return_value.run.return_value = []
        result = stub_rdb["Processed"].list_table_rows("videos")
        assert result == []


class TestListVideoIds:
    def test_returns_id_list(self, stub_rdb):
        rows = [{"id": "v1"}, {"id": "v2"}, {"id": "v3"}]
        stub_rdb["mock_table"].return_value.pluck.return_value.run.return_value = rows
        result = stub_rdb["Processed"].list_video_ids()
        assert result == ["v1", "v2", "v3"]
        stub_rdb["mock_table"].assert_any_call("videos")
        stub_rdb["mock_table"].return_value.pluck.assert_called_with("id")

    def test_empty_list_when_no_videos(self, stub_rdb):
        stub_rdb["mock_table"].return_value.pluck.return_value.run.return_value = []
        assert stub_rdb["Processed"].list_video_ids() == []


class TestFindUserKindByUrl:
    def test_returns_match(self, stub_rdb):
        rows = [{"id": "d1", "url-isard": "u1", "user": "user-1"}]
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = rows
        result = stub_rdb["Processed"].find_user_kind_by_url("domains", "user-1", "u1")
        assert result == rows
        stub_rdb["mock_table"].assert_any_call("domains")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "u1", index="url-isard"
        )
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.assert_called_with(
            {"user": "user-1"}
        )

    def test_empty_when_no_match(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = []
        assert (
            stub_rdb["Processed"].find_user_kind_by_url("media", "user-1", "u-missing")
            == []
        )


class TestFindUserKindByUrlWeb:
    def test_returns_match_via_url_web(self, stub_rdb):
        rows = [{"id": "m1", "url-web": "http://x", "user": "user-1"}]
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.filter.return_value.run.return_value = rows
        result = stub_rdb["Processed"].find_user_kind_by_url_web(
            "media", "user-1", "http://x"
        )
        assert result == rows
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "http://x", index="url-web"
        )


class TestGetUserMetadata:
    def test_returns_plucked_user(self, stub_rdb):
        user = {
            "id": "user-1",
            "category": "cat-1",
            "group": "grp-1",
            "provider": "local",
            "username": "alice",
            "uid": "alice-uid",
        }
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = user
        result = stub_rdb["Processed"].get_user_metadata("user-1")
        assert result == user
        stub_rdb["mock_table"].assert_any_call("users")
        stub_rdb["mock_table"].return_value.get.assert_called_with("user-1")
        stub_rdb["mock_table"].return_value.get.return_value.pluck.assert_called_with(
            "id", "category", "group", "provider", "username", "uid"
        )
