#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Restarting the temporal desktop the old frontend reuses per template.

That restart is a real start, so a GPU desktop needs a booking for it: the one
it last ran under has ended. Unlike the create path there is no rollback here
-- the desktop pre-exists, so a booking that doesn't fit must leave it stopped
and re-startable rather than delete it.
"""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops_nonpersistent as mod

DNP = mod.DesktopsNonpersistentProcessed

END = "2026-09-07T18:30+0000"

GPU_DESKTOP = {
    "id": "d-1",
    "status": "Stopped",
    "booking_id": False,
    "create_dict": {"reservables": {"vgpus": ["NVIDIA-A16-2Q"]}},
}


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(DNP, "_rdb_context", classmethod(lambda cls: nullcontext()))
    # Metaclass property: patching it on DNP itself can't be undone on teardown.
    monkeypatch.setattr(type(DNP), "_rdb_connection", property(lambda cls: None))

    desktops = []
    monkeypatch.setattr(
        DNP, "user_template_desktops", classmethod(lambda cls, u, t: desktops)
    )
    start = MagicMock()
    monkeypatch.setattr(mod.DesktopEvents, "desktop_start", staticmethod(start))
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "check_virt_storage_pool_availability",
        staticmethod(MagicMock()),
    )
    monkeypatch.setattr(
        mod.Scheduler, "add_desktop_timeouts", staticmethod(MagicMock())
    )
    monkeypatch.setattr(
        mod.Helpers, "gen_payload_from_user", staticmethod(lambda user: {})
    )
    booking = MagicMock()
    monkeypatch.setattr(mod.BookingsProcessed, "add", staticmethod(booking))
    return {"desktops": desktops, "start": start, "booking": booking}


def test_a_stopped_gpu_desktop_is_booked_before_it_restarts(stub):
    stub["desktops"].append(dict(GPU_DESKTOP))

    assert (
        DNP._single_desktop_per_template("u-1", "t-1", None, None, booking_end=END)
        == "d-1"
    )

    stub["booking"].assert_called_once()
    args, kwargs = stub["booking"].call_args
    assert args[2] == END
    assert args[4] == "d-1"
    assert kwargs["now"] is True
    stub["start"].assert_called_once_with("d-1")


def test_restarting_a_gpu_desktop_without_an_end_time_is_refused(stub):
    stub["desktops"].append(dict(GPU_DESKTOP))

    with pytest.raises(Error) as excinfo:
        DNP._single_desktop_per_template("u-1", "t-1", None, None)

    assert (
        excinfo.value.error["description_code"] == "temporal_reservable_needs_booking"
    )
    # Left exactly as it was: still stopped, still startable once booked.
    stub["start"].assert_not_called()


def test_a_desktop_still_inside_its_booking_is_not_booked_again(stub):
    stub["desktops"].append({**GPU_DESKTOP, "booking_id": "b-1"})

    DNP._single_desktop_per_template("u-1", "t-1", None, None)

    stub["booking"].assert_not_called()
    stub["start"].assert_called_once_with("d-1")


def test_a_desktop_without_a_vgpu_restarts_unbooked(stub):
    stub["desktops"].append(
        {"id": "d-2", "status": "Stopped", "create_dict": {"reservables": {}}}
    )

    DNP._single_desktop_per_template("u-1", "t-1", None, None)

    stub["booking"].assert_not_called()
    stub["start"].assert_called_once_with("d-2")


def test_an_already_started_desktop_is_neither_booked_nor_restarted(stub):
    stub["desktops"].append({**GPU_DESKTOP, "status": "Started"})

    assert DNP._single_desktop_per_template("u-1", "t-1", None, None) == "d-1"

    stub["booking"].assert_not_called()
    stub["start"].assert_not_called()
