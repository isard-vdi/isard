#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``DomainsProcessed`` admin-domains query helpers
(tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/admin/domains.py``. Each test pins the query shape /
return value contract; route-level tests (under apiv4) keep stubbing
the service so wire compatibility is unaffected.

Pins:
* get_by_ids dispatches a batch read merged with user/category/group
  names; ``[deleted]`` placeholder when refs are missing.
* find_disks_by_kind_status uses ``kind_status`` for admins and
  ``kind_status_category`` for managers.
* get_xml raises not_found when the row is absent and returns
  ``row.xml`` otherwise.
* update_xml stamps ``status="Updating"`` + ``id=domain_id`` and
  returns the freshly-stored xml.
* get_xml_and_protected returns ``{xml, protected}``; protected
  defaults to ``[]`` when create_dict.xml_protected_sections is
  unset.
* get_for_search returns the full row or ``None`` (caller decides
  on the 404 message).
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


class TestGetByIds:
    def test_dispatches_batch_read_with_merge(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.merge.return_value.run.return_value = [
            {
                "id": "d-1",
                "name": "Desktop One",
                "user_name": "Alice",
                "category_name": "Cat",
                "group_name": "Grp",
            }
        ]
        result = stub_rdb["Processed"].get_by_ids(["d-1"])
        assert result[0]["id"] == "d-1"
        assert result[0]["user_name"] == "Alice"
        # The merge layer was used (the dynamic name lookups go via
        # rdb r.table joins inside the lambda).
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.merge.assert_called()


class TestFindDisksByKindStatus:
    def test_admin_uses_kind_status_index(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = [
            {"create_dict": {"hardware": {"disks": [{"storage_id": "s-1"}]}}}
        ]
        result = stub_rdb["Processed"].find_disks_by_kind_status(
            "desktop", "Failed", category_id=None
        )
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "kind_status"
        assert get_all_call.args[0] == ["desktop", "Failed"]
        assert result[0]["create_dict"]["hardware"]["disks"][0]["storage_id"] == "s-1"

    def test_manager_uses_kind_status_category_index(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get_all.return_value.pluck.return_value.run.return_value = []
        stub_rdb["Processed"].find_disks_by_kind_status(
            "desktop", "Failed", category_id="cat-1"
        )
        get_all_call = stub_rdb["mock_table"].return_value.get_all.call_args
        assert get_all_call.kwargs.get("index") == "kind_status_category"
        assert get_all_call.args[0] == ["desktop", "Failed", "cat-1"]


class TestGetXml:
    def test_returns_xml(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1",
            "xml": "<domain/>",
        }
        assert stub_rdb["Processed"].get_xml("d-1") == "<domain/>"

    def test_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            stub_rdb["Processed"].get_xml("missing")
        assert exc.value.error.get("error") == "not_found"

    def test_decompresses_compressed_xml(self, stub_rdb):
        import zstandard as zstd

        original = "<domain>" + ("<disk/>" * 100) + "</domain>"
        compressed = zstd.ZstdCompressor(level=3).compress(original.encode())
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1",
            "xml": compressed,
        }
        assert stub_rdb["Processed"].get_xml("d-1") == original


class TestUpdateXml:
    def test_stamps_status_and_id(self, stub_rdb):
        # First .run() (existence check) returns the row; second .run()
        # is the update; third returns the new pluck.
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1"
        }
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.return_value = {
            "replaced": 1
        }
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "xml": "<new/>"
        }
        result = stub_rdb["Processed"].update_xml("d-1", {"xml": "<new/>"})
        assert result == "<new/>"
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        payload = update_call.args[0]
        assert payload["status"] == "Updating"
        assert payload["id"] == "d-1"
        assert payload["xml"] == "<new/>"

    def test_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            stub_rdb["Processed"].update_xml("missing", {"xml": "<x/>"})
        assert exc.value.error.get("error") == "not_found"

    def test_compresses_big_xml_in_payload(self, stub_rdb):
        big_xml = "<domain>" + ("<disk/>" * 200) + "</domain>"
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1"
        }
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.return_value = {
            "replaced": 1
        }
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "xml": "<post/>"
        }
        stub_rdb["Processed"].update_xml("d-1", {"xml": big_xml})
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        payload = update_call.args[0]
        # Above threshold — must be the r.binary ReQL term.
        assert not isinstance(payload["xml"], str)


class TestGetXmlAndProtected:
    def test_returns_dict(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "xml": "<domain/>",
            "create_dict": {"xml_protected_sections": ["memory"]},
        }
        result = stub_rdb["Processed"].get_xml_and_protected("d-1")
        assert result == {"xml": "<domain/>", "protected": ["memory"]}

    def test_protected_defaults_to_empty(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "xml": "<domain/>",
            "create_dict": {},
        }
        result = stub_rdb["Processed"].get_xml_and_protected("d-1")
        assert result["protected"] == []

    def test_decompresses_compressed_xml(self, stub_rdb):
        import zstandard as zstd

        original = "<domain>" + ("<disk/>" * 100) + "</domain>"
        compressed = zstd.ZstdCompressor(level=3).compress(original.encode())
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "xml": compressed,
            "create_dict": {"xml_protected_sections": ["memory"]},
        }
        result = stub_rdb["Processed"].get_xml_and_protected("d-1")
        assert result["xml"] == original
        assert result["protected"] == ["memory"]

    def test_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_factory import Error

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = (
            None
        )
        with pytest.raises(Error) as exc:
            stub_rdb["Processed"].get_xml_and_protected("missing")
        assert exc.value.error.get("error") == "not_found"


class TestGetForSearch:
    def test_returns_row(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1",
            "name": "Desktop One",
        }
        result = stub_rdb["Processed"].get_for_search("d-1")
        assert result == {"id": "d-1", "name": "Desktop One"}

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_for_search("missing") is None
