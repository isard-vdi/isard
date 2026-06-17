#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Booking gate on the direct-viewer token-start path.

Regression guard for ``DesktopDirectViewer.start_desktop`` (served by
``PUT /item/desktop/token/{token}/start-desktop``). A bookable (e.g. vGPU)
desktop must not start outside an active booking — otherwise a share-token
holder could launch it bypassing the reservation system. The same gate is
enforced by the viewer-open path (``desktop_viewer_from_token``); both now
share ``_ensure_bookable_or_raise``.

Pins:
* non-bookable desktop starts normally,
* bookable desktop with no booking → 428 ``desktop_not_booked``, no start,
* bookable desktop whose next booking is in the future → 428
  ``desktop_not_booked_until``, no start,
* bookable desktop inside an active booking starts normally.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktop_direct_viewer as mod

DDV = mod.DesktopDirectViewer
STOPPED = mod.DesktopStatusEnum.stopped.value


@pytest.fixture
def stub(monkeypatch):
    domain = {"id": "d-1", "status": STOPPED, "user": "u-1"}
    monkeypatch.setattr(
        DDV, "get_desktop_from_token", classmethod(lambda cls, token: dict(domain))
    )
    start = MagicMock(name="desktop_start")
    monkeypatch.setattr(mod.DesktopEvents, "desktop_start", staticmethod(start))
    monkeypatch.setattr(
        mod.Logging, "logs_domain_start_directviewer", staticmethod(MagicMock())
    )
    monkeypatch.setattr(
        mod.Helpers,
        "gen_payload_from_user",
        staticmethod(lambda user: {"user_id": user}),
    )
    monkeypatch.setattr(
        mod.Scheduler,
        "add_desktop_timeouts",
        staticmethod(MagicMock(return_value=False)),
    )
    return {"start": start}


def _set_booking(monkeypatch, **booking):
    monkeypatch.setattr(
        mod.DesktopsProcessed,
        "_parse_desktop_booking",
        classmethod(lambda cls, d: booking),
    )


class TestDirectViewerStartBookingGate:
    def test_non_bookable_starts(self, stub, monkeypatch):
        _set_booking(monkeypatch, needs_booking=False)
        assert DDV.start_desktop("tok", request=None) == "d-1"
        stub["start"].assert_called_once()

    def test_bookable_without_booking_raises_and_does_not_start(
        self, stub, monkeypatch
    ):
        _set_booking(monkeypatch, needs_booking=True, next_booking_start=None)
        with pytest.raises(Error) as exc:
            DDV.start_desktop("tok", request=None)
        assert exc.value.error["description_code"] == "desktop_not_booked"
        stub["start"].assert_not_called()

    def test_bookable_future_booking_raises_and_does_not_start(self, stub, monkeypatch):
        _set_booking(
            monkeypatch,
            needs_booking=True,
            next_booking_start="2999-01-01T00:00+0000",
        )
        monkeypatch.setattr(mod.Helpers, "is_future", staticmethod(lambda b: True))
        with pytest.raises(Error) as exc:
            DDV.start_desktop("tok", request=None)
        assert exc.value.error["description_code"] == "desktop_not_booked_until"
        stub["start"].assert_not_called()

    def test_bookable_active_booking_starts(self, stub, monkeypatch):
        _set_booking(
            monkeypatch,
            needs_booking=True,
            next_booking_start="2020-01-01T00:00+0000",
        )
        monkeypatch.setattr(mod.Helpers, "is_future", staticmethod(lambda b: False))
        assert DDV.start_desktop("tok", request=None) == "d-1"
        stub["start"].assert_called_once()
