#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``convert_template_to_desktop`` and ``update_storage``.

convert_template_to_desktop rejects, before touching the template's disk:

* an unknown template (L1236) not_found;
* a template that is itself a duplicate (L1249) duplicate;
* a template with dependent items in the recycle bin (L1266)
  storage_has_recycled_children.

update_storage rejects:

* an unknown domain (L1992) not_found;
* a domain that is not stopped/in maintenance (L1999) precondition_required;
and only writes the new disk for a ``desktop``-kind domain (L2005).

Both run unmocked; the schema, the ``Domain`` model, the recycle-bin helper
and rethink are stubbed, so each reject decision is the real code.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestConvertTemplateToDesktopGuards:
    @pytest.fixture
    def env(self, monkeypatch):
        state = {"exists": True, "is_duplicate": False, "recycled": []}

        monkeypatch.setattr(
            mod, "TemplateToDesktop", lambda **d: SimpleNamespace(model_dump=lambda: d)
        )

        class FakeDomain:
            @staticmethod
            def exists(tid):
                return state["exists"]

            def __init__(self, tid):
                self.user = "owner"

        monkeypatch.setattr(mod, "Domain", FakeDomain)
        monkeypatch.setattr(
            mod.Helpers,
            "check_user_duplicated_domain_name",
            classmethod(lambda cls, *a, **k: None),
        )
        monkeypatch.setattr(
            mod.TemplatesProcessed,
            "is_duplicate",
            classmethod(lambda cls, tid: state["is_duplicate"]),
        )
        monkeypatch.setattr(
            mod.RecycleBinHelpers,
            "get_template_dependant_recycle_bin_entries",
            classmethod(lambda cls, ids, field: state["recycled"]),
        )
        return state

    def test_template_not_found(self, env):
        env["exists"] = False
        with pytest.raises(Error) as exc:
            DP.convert_template_to_desktop({"template_id": "t-1", "name": "d"})
        assert exc.value.error["error"] == "not_found"

    def test_duplicate_template_rejected(self, env):
        env["is_duplicate"] = True
        with pytest.raises(Error) as exc:
            DP.convert_template_to_desktop({"template_id": "t-1", "name": "d"})
        assert exc.value.error["description_code"] == "duplicate"

    def test_recycled_dependants_block_conversion(self, env):
        env["recycled"] = [{"id": "r-1"}]
        with pytest.raises(Error) as exc:
            DP.convert_template_to_desktop({"template_id": "t-1", "name": "d"})
        assert exc.value.error["description_code"] == "storage_has_recycled_children"


class TestUpdateStorageGuards:
    @pytest.fixture
    def rdb(self, monkeypatch):
        state = {"domain": {"status": "Stopped", "kind": "desktop"}}
        monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
        monkeypatch.setattr(
            type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
        )
        tbl = MagicMock(name="r.table(domains)")
        tbl.get.return_value.run.return_value = state["domain"]
        monkeypatch.setattr(mod.r, "table", lambda name: tbl)
        state["tbl"] = tbl
        return state

    def test_domain_not_found(self, rdb):
        rdb["tbl"].get.return_value.run.return_value = None
        with pytest.raises(Error) as exc:
            DP.update_storage("d-1", "st-new")
        assert exc.value.error["description_code"] == "not_found"

    def test_must_be_stopped(self, rdb):
        rdb["tbl"].get.return_value.run.return_value = {
            "status": "Started",
            "kind": "desktop",
        }
        with pytest.raises(Error) as exc:
            DP.update_storage("d-1", "st-new")
        assert exc.value.error["error"] == "precondition_required"

    def test_stopped_desktop_updates_and_returns_id(self, rdb):
        rdb["tbl"].get.return_value.run.return_value = {
            "status": "Stopped",
            "kind": "desktop",
        }
        assert DP.update_storage("d-1", "st-new") == "d-1"
        rdb["tbl"].get.return_value.update.assert_called_once()
