#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A temporal desktop with a vGPU is booked as part of its creation.

The engine attaches the vGPU straight from ``create_dict.reservables`` when
``start_after_created`` fires, without ever consulting ``bookings``, so a
temporal GPU desktop created without a reservation would take a profile behind
the planner's back. It is booked between the insert and the disk chain, while
the row is still inert and the whole create can be undone.
"""

import copy
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
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

END = "2026-09-07T18:30+0000"


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

    calls = []
    storage = MagicMock(id="s-new", path="/isard/s-new.qcow2")
    storage.enqueue_disk_creation_chain_for_domain.side_effect = (
        lambda **kw: calls.append("chain")
    )
    monkeypatch.setattr(mod.Storage, "new_dict", staticmethod(lambda **kw: storage))
    monkeypatch.setattr(
        mod, "DomainModel", lambda **row: SimpleNamespace(model_dump=lambda: row)
    )

    # The template carries a vGPU unless a test says otherwise.
    reservables = {"vgpus": ["NVIDIA-A16-2Q"]}
    merged = {
        "hardware": {"vcpus": 4, "memory": 2, "interfaces": ["default"]},
        "reservables": reservables,
    }
    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "merge_new_data_with_template",
        staticmethod(lambda template_id, new_data: (merged, {})),
    )
    monkeypatch.setattr(
        mod.Quotas,
        "limit_user_hardware_allowed",
        staticmethod(lambda payload, create_dict: create_dict),
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", staticmethod(lambda user_id: {})
    )
    monkeypatch.setattr(mod.Cards, "update", staticmethod(MagicMock()))
    monkeypatch.setattr(mod.Cards, "upload", staticmethod(MagicMock()))

    booking = MagicMock(side_effect=lambda *a, **kw: calls.append("booking"))
    monkeypatch.setattr(mod.BookingsProcessed, "add", staticmethod(booking))
    delete_bookings = MagicMock()
    monkeypatch.setattr(
        mod.BookingsProcessed, "delete_item_bookings", staticmethod(delete_bookings)
    )
    domain_delete = MagicMock()
    monkeypatch.setattr(mod.Domain, "delete_document_if", staticmethod(domain_delete))
    storage_delete = MagicMock()
    monkeypatch.setattr(mod.Storage, "delete_document_if", staticmethod(storage_delete))

    return {
        "domains": tables["domains"],
        "storage": storage,
        "booking": booking,
        "delete_bookings": delete_bookings,
        "domain_delete": domain_delete,
        "storage_delete": storage_delete,
        "calls": calls,
        "reservables": reservables,
    }


def _inserted(stub):
    return stub["domains"].insert.call_args[0][0]


def test_the_vgpu_lands_on_the_desktop_row(stub):
    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="gpu", booking_end=END)

    assert _inserted(stub)["create_dict"]["reservables"] == {"vgpus": ["NVIDIA-A16-2Q"]}


def test_the_booking_is_made_before_the_disk_chain(stub):
    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="gpu", booking_end=END)

    # Booked while the row is still inert: once the chain is enqueued the
    # engine owns the desktop and a rollback would race the disk task.
    assert stub["calls"] == ["booking", "chain"]
    args, kwargs = stub["booking"].call_args
    assert args[2] == END
    assert args[3] == "desktop"
    assert args[4] == _inserted(stub)["id"]
    assert kwargs["now"] is True


def test_a_vgpu_without_a_booking_end_is_refused(stub):
    with pytest.raises(Error) as excinfo:
        DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="gpu")

    assert (
        excinfo.value.error["description_code"] == "temporal_reservable_needs_booking"
    )
    stub["domains"].insert.assert_not_called()
    stub["booking"].assert_not_called()


def test_a_refused_booking_leaves_nothing_behind(stub):
    stub["booking"].side_effect = Error("conflict", "nope")

    with pytest.raises(Error):
        DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="gpu", booking_end=END)

    desktop_id = _inserted(stub)["id"]
    stub["delete_bookings"].assert_called_once_with("desktop", desktop_id)
    stub["domain_delete"].assert_called_once_with(
        desktop_id, field="status", values=["CreatingAndStarting"]
    )
    stub["storage_delete"].assert_called_once_with(
        "s-new", field="status", values=["non_existing"]
    )
    stub["storage"].enqueue_disk_creation_chain_for_domain.assert_not_called()


def test_a_failed_disk_chain_rolls_back_too(stub):
    stub["storage"].enqueue_disk_creation_chain_for_domain.side_effect = Error(
        "precondition_required", "no parent"
    )

    with pytest.raises(Error):
        DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="gpu", booking_end=END)

    # Otherwise the desktop is left stuck in CreatingAndStarting forever.
    stub["domain_delete"].assert_called_once()
    stub["storage_delete"].assert_called_once()


def test_a_desktop_without_a_vgpu_is_never_booked(stub):
    stub["reservables"]["vgpus"] = None

    DNP._nonpersistent_desktop_from_tmpl("u-1", "t-1", name="plain", booking_end=END)

    stub["booking"].assert_not_called()
    assert stub["calls"] == ["chain"]


def test_a_quota_stripped_vgpu_needs_no_booking(stub, monkeypatch):
    # The quota can remove every profile the user isn't allowed, so the
    # decision has to read what survives it, not what was asked for.
    def strip(payload, create_dict):
        create_dict["reservables"] = {"vgpus": None}
        return create_dict

    monkeypatch.setattr(mod.Quotas, "limit_user_hardware_allowed", staticmethod(strip))

    DNP._nonpersistent_desktop_from_tmpl(
        "u-1", "t-1", name="plain", new_data={"hardware": {}}, booking_end=END
    )

    stub["booking"].assert_not_called()
