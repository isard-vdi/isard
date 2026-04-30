#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Alloweds`` raw-dict CRUD methods (tier 3.4 batch 1).

Migrated from inline rethink queries previously in apiv4's
``services/admin/alloweds.py``. Pins:

* update_item_allowed_dict dispatches a partial update to ``allowed``.
* get_item_allowed_dict reads ``.allowed`` field via pluck; returns
  empty dict when row is missing.
* get_bastion_allowed_dict / get_bastion_domains_allowed_dict read
  config[id=1] and use ``.default(...)`` so a fresh deployment without
  bastion config returns ``{}``.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.helpers import alloweds as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Alloweds, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Alloweds),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Alloweds": mod.Alloweds}


class TestUpdateItemAllowedDict:
    def test_dispatches_update(self, stub_rdb):
        stub_rdb["Alloweds"].update_item_allowed_dict(
            "media", "m-1", {"users": ["u-a"], "roles": False}
        )
        update_call = stub_rdb[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list[-1]
        assert update_call.args[0] == {"allowed": {"users": ["u-a"], "roles": False}}


class TestGetItemAllowedDict:
    def test_returns_allowed_field(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "allowed": {"users": ["u-a"]}
        }
        assert stub_rdb["Alloweds"].get_item_allowed_dict("media", "m-1") == {
            "users": ["u-a"]
        }

    def test_returns_empty_when_row_missing(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = None
        assert stub_rdb["Alloweds"].get_item_allowed_dict("media", "missing") == {}


class TestBastionAllowedDicts:
    def test_get_bastion_allowed_returns_block(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "bastion": {"allowed": {"roles": ["admin"]}}
        }
        assert stub_rdb["Alloweds"].get_bastion_allowed_dict() == {"roles": ["admin"]}

    def test_get_bastion_allowed_empty_when_unset(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "bastion": {"allowed": {}}
        }
        assert stub_rdb["Alloweds"].get_bastion_allowed_dict() == {}

    def test_get_bastion_domains_allowed_returns_block(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.default.return_value.run.return_value = {
            "bastion": {"individual_domains": {"allowed": {"users": ["u-a"]}}}
        }
        assert stub_rdb["Alloweds"].get_bastion_domains_allowed_dict() == {
            "users": ["u-a"]
        }
