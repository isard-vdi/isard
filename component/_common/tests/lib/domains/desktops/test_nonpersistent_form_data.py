#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A temporal desktop keeps the submitted configuration.

Everything the new frontend sends (hardware, viewers, card) used to be dropped
in favour of the template's own values; the old frontend sends none of it and
must keep inheriting the template as it did on v3.
"""

import copy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.domains.desktops import desktops_nonpersistent as mod

DNP = mod.DesktopsNonpersistentProcessed

TEMPLATE = {
    "id": "t-1",
    "name": "template",
    "description": "template description",
    "create_dict": {"hardware": {"disks": [{"storage_id": "s-parent"}]}},
    "guest_properties": {"viewers": {"spice": {}}},
    "hypervisors_pools": ["default"],
    "image": {"id": "template-card", "type": "stock"},
    "parents": [],
}


def _merged():
    return (
        {"hardware": {"vcpus": 4, "memory": 2, "interfaces": ["default"]}},
        {"viewers": {"browser": {}}},
    )


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(DNP, "_rdb_context", classmethod(lambda cls: nullcontext()))
    # Metaclass property: patching it on DNP itself can't be undone on teardown.
    monkeypatch.setattr(type(DNP), "_rdb_connection", property(lambda cls: None))

    tables = {"domains": MagicMock(), "users": MagicMock(), "groups": MagicMock()}
    tables["domains"].get.return_value.run.return_value = copy.deepcopy(TEMPLATE)
    tables["users"].get.return_value.run.return_value = {
        "id": "u-1",
        "username": "user",
        "category": "c-1",
        "group": "g-1",
    }
    tables["groups"].get.return_value.run.return_value = {"id": "g-1"}
    rethink = MagicMock()
    rethink.table.side_effect = lambda name: tables[name]
    monkeypatch.setattr(mod, "r", rethink)

    storage = MagicMock(id="s-new", path="/isard/s-new.qcow2")
    monkeypatch.setattr(mod.Storage, "new_dict", staticmethod(lambda **kw: storage))
    monkeypatch.setattr(
        mod, "DomainModel", lambda **row: SimpleNamespace(model_dump=lambda: row)
    )
    merge = MagicMock(side_effect=lambda template_id, new_data: _merged())
    monkeypatch.setattr(
        mod.DesktopsProcessed, "merge_new_data_with_template", staticmethod(merge)
    )
    limit = MagicMock(side_effect=lambda payload, create_dict: create_dict)
    monkeypatch.setattr(mod.Quotas, "limit_user_hardware_allowed", staticmethod(limit))
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", staticmethod(lambda user_id: {})
    )
    cards = MagicMock()
    monkeypatch.setattr(mod.Cards, "update", staticmethod(cards.update))
    monkeypatch.setattr(mod.Cards, "upload", staticmethod(cards.upload))
    return {
        "domains": tables["domains"],
        "merge": merge,
        "limit": limit,
        "cards": cards,
    }


def _inserted(stub):
    return stub["domains"].insert.call_args[0][0]


def test_form_data_lands_on_the_desktop(stub):
    new_data = {"hardware": {"vcpus": 4}}

    DNP._nonpersistent_desktop_from_tmpl(
        "u-1",
        "t-1",
        name="mine",
        description="mine too",
        new_data=new_data,
        image={"id": "chosen-card", "type": "stock"},
    )

    stub["merge"].assert_called_once_with("t-1", new_data)
    row = _inserted(stub)
    assert row["name"] == "mine"
    assert row["description"] == "mine too"
    assert row["create_dict"]["hardware"]["vcpus"] == 4
    assert row["guest_properties"] == {"viewers": {"browser": {}}}
    assert row["image"] == {"id": "chosen-card", "type": "stock"}
    stub["cards"].update.assert_called_once_with(row["id"], "chosen-card", "stock")
    stub["limit"].assert_called_once()


def test_uploaded_card_goes_through_upload(stub):
    image = {"id": "chosen-card", "type": "user", "file": "data:image/png;base64,x"}

    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="mine", image=image)

    stub["cards"].upload.assert_called_once_with(_inserted(stub)["id"], image)
    stub["cards"].update.assert_not_called()


def test_without_form_data_the_template_is_inherited(stub):
    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="mine")

    stub["merge"].assert_called_once_with("t-1", None)
    row = _inserted(stub)
    assert row["description"] == "template description"
    assert row["image"] == {"id": "template-card", "type": "stock"}
    # The old frontend sends no hardware, so nothing gets trimmed on its behalf.
    stub["limit"].assert_not_called()
    stub["cards"].update.assert_not_called()


def test_memory_is_stored_in_kib(stub):
    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="mine")

    assert _inserted(stub)["create_dict"]["hardware"]["memory"] == 2 * 1048576
