#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``XmlSectionsProcessed`` (tier 3.4 batch 2).

Migrated from inline rethink queries previously living in apiv4's
``services/xml_sections.py``. The pure-XML splitting/merging helpers
stay in apiv4 (no rdb access there); only the table-level queries
moved to ``_common`` and are pinned here.

Pins:
* update_domain_xml_and_protected dispatches a merge that wraps
  ``protected_sections`` in ``r.literal(...)`` so removed sections
  actually disappear (otherwise rdb merges nested arrays).
* get_domain_capabilities returns the first hyp's caps or ``{}`` when
  none reported.
* get_domain / get_virt_install return ``None`` when the row is missing.
* update_virt_install_xml dispatches a partial update with just ``xml``.
* insert_virt_install dispatches a vanilla insert.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.domains import xml_sections as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.XmlSectionsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.XmlSectionsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "literal", lambda x: ("LITERAL", x))
    yield {"mock_table": mock_table, "Processed": mod.XmlSectionsProcessed}


class TestUpdateDomainXmlAndProtected:
    def test_dispatches_merge_with_literal(self, stub_rdb):
        stub_rdb["Processed"].update_domain_xml_and_protected(
            "d-1", "<domain/>", ["memory", "vcpus"]
        )
        stub_rdb["mock_table"].assert_any_call("domains")
        stub_rdb["mock_table"].return_value.get.assert_any_call("d-1")
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        payload = update_call.args[0]
        # Below the 512-byte threshold — compress_xml returns the
        # original str unchanged.
        assert payload["xml"] == "<domain/>"
        # The list is wrapped in r.literal(...) — our stub returns a
        # ("LITERAL", value) tuple so we can assert the wrapping.
        assert payload["create_dict"]["xml_protected_sections"] == (
            "LITERAL",
            ["memory", "vcpus"],
        )

    def test_compresses_xml_above_threshold(self, stub_rdb):
        big_xml = "<domain>" + ("<disk dev='vda'/>" * 200) + "</domain>"
        stub_rdb["Processed"].update_domain_xml_and_protected("d-1", big_xml, [])
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        payload = update_call.args[0]
        # Above threshold — must be the r.binary ReQL term, not str.
        assert not isinstance(payload["xml"], str)
        # The Binary term carries base64-encoded zstd bytes.
        import base64

        raw = base64.b64decode(payload["xml"].base64_data)
        assert raw[:4] == b"\x28\xb5\x2f\xfd"  # zstd magic


class TestGetDomainCapabilities:
    def test_returns_caps_from_first_hyp(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.has_fields.return_value.filter.return_value.pluck.return_value.limit.return_value.run.return_value = [
            {"info": {"domain_capabilities": {"machine_types": ["q35"]}}}
        ]
        result = stub_rdb["Processed"].get_domain_capabilities()
        assert result == {"machine_types": ["q35"]}

    def test_returns_empty_when_no_hyps(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.has_fields.return_value.filter.return_value.pluck.return_value.limit.return_value.run.return_value = (
            []
        )
        assert stub_rdb["Processed"].get_domain_capabilities() == {}


class TestGetDomain:
    def test_returns_row(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "d-1",
            "xml": "<domain/>",
        }
        result = stub_rdb["Processed"].get_domain("d-1")
        assert result == {"id": "d-1", "xml": "<domain/>"}

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_domain("missing") is None

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
        result = stub_rdb["Processed"].get_domain("d-1")
        assert result["xml"] == original


class TestGetVirtInstall:
    def test_returns_row(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = {
            "id": "vi-1",
            "xml": "<domain/>",
        }
        result = stub_rdb["Processed"].get_virt_install("vi-1")
        assert result == {"id": "vi-1", "xml": "<domain/>"}

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.default.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_virt_install("missing") is None


class TestUpdateVirtInstallXml:
    def test_dispatches_partial_update(self, stub_rdb):
        stub_rdb["Processed"].update_virt_install_xml("vi-1", "<merged/>")
        stub_rdb["mock_table"].assert_any_call("virt_install")
        stub_rdb["mock_table"].return_value.get.assert_any_call("vi-1")
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"xml": "<merged/>"}


class TestInsertVirtInstall:
    def test_dispatches_insert(self, stub_rdb):
        record = {
            "id": "my_template",
            "name": "My template",
            "xml": "<domain/>",
            "icon": "linux",
            "vers": "",
            "www": "",
        }
        stub_rdb["Processed"].insert_virt_install(record)
        stub_rdb["mock_table"].assert_any_call("virt_install")
        insert_call = stub_rdb["mock_table"].return_value.insert.call_args_list[-1]
        assert insert_call.args[0] == record
