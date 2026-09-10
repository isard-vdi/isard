#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DesktopsProcessed.check_max_booking_date``.

Computes how long a bookable desktop may run and rejects when it cannot
run long enough. The gates pinned:

* the user's priority grants no time at all -> reject (L1858)
  bookings_max_time_reached;
* a non-admin without enough advance time -> reject (L1867)
  not_enough_advanced_time, while an admin bypasses that gate (L1884);
* the computed window is below the minimum: a deployment desktop rejects
  with needs_deployment_booking (L1898), a standalone with
  not_enough_time_to_start (L1904);
* otherwise a max-booking-date string is returned.

``check_max_booking_date`` runs unmocked; ``check_current_plan`` and the
priority/reservable collaborators are stubbed, so every reject threshold is
evaluated by the real code (``MIN_AUTOBOOKING_TIME`` = 30).
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed
FAR_FUTURE = "2999-01-01T00:00+0000"


@pytest.fixture
def env(monkeypatch):
    """Stub the plan + priority collaborators; tests tune the numbers."""
    state = {
        "priority_max_time": 60,  # users_priority["max_time"]
        "forbid_time": 60,
        "profile_max_time": 60,
        "desktop": {"tag": False},
    }
    monkeypatch.setattr(
        DP,
        "check_current_plan",
        classmethod(lambda cls, payload, did: [{"end": FAR_FUTURE}]),
    )
    monkeypatch.setattr(
        mod.BookingsHelpers,
        "_get_reservables",
        staticmethod(lambda kind, did: ([], 1, "name")),
    )
    monkeypatch.setattr(
        mod.ReservablesPlannerCompute,
        "payload_priority",
        staticmethod(
            lambda payload, reservables: {"max_time": state["priority_max_time"]}
        ),
    )
    monkeypatch.setattr(
        mod.BookingsProcessed,
        "get_min_profile_priority",
        staticmethod(
            lambda kind, did: {
                "forbid_time": state["forbid_time"],
                "max_time": state["profile_max_time"],
            }
        ),
    )
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, t, d: state["desktop"])
    )
    return state


def _payload(role_id="advanced"):
    return {"role_id": role_id, "user_id": "u-1"}


class TestCheckMaxBookingDateGuards:
    def test_no_priority_time_rejected(self, env):
        env["priority_max_time"] = 0
        with pytest.raises(Error) as exc:
            DP.check_max_booking_date(_payload(), "d-1")
        assert exc.value.error["description_code"] == "bookings_max_time_reached"

    def test_non_admin_without_advance_time_rejected(self, env):
        env["forbid_time"] = 10  # < MIN_AUTOBOOKING_TIME (30)
        with pytest.raises(Error) as exc:
            DP.check_max_booking_date(_payload("advanced"), "d-1")
        assert exc.value.error["description_code"] == "not_enough_advanced_time"

    def test_admin_bypasses_advance_time_gate(self, env):
        # Same tiny forbid_time, but an admin is not blocked by it and, with
        # ample max/available time, gets a booking date back.
        env["forbid_time"] = 10
        result = DP.check_max_booking_date(_payload("admin"), "d-1")
        assert isinstance(result, str)

    def test_insufficient_window_deployment_desktop(self, env):
        # forbid_time passes the advance gate (>=30) but max_time collapses the
        # window below the minimum -> deployment-specific reject.
        env["forbid_time"] = 30
        env["profile_max_time"] = 1
        env["desktop"] = {"tag": "dep-1"}
        with pytest.raises(Error) as exc:
            DP.check_max_booking_date(_payload("advanced"), "d-1")
        assert exc.value.error["description_code"] == "needs_deployment_booking"

    def test_insufficient_window_standalone_desktop(self, env):
        env["forbid_time"] = 30
        env["profile_max_time"] = 1
        env["desktop"] = {"tag": False}
        with pytest.raises(Error) as exc:
            DP.check_max_booking_date(_payload("advanced"), "d-1")
        assert exc.value.error["description_code"] == "not_enough_time_to_start"
