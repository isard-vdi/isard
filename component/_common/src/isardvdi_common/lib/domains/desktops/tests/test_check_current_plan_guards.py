#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``DesktopsProcessed.check_current_plan`` — the booking gate.

A bookable desktop can only start if it currently sits inside an active
plan. When it does not, the reject differs by whether the desktop belongs
to a deployment:

* no active plan + deployment desktop -> reject (L1832) needs_deployment_booking;
* no active plan + standalone desktop -> reject (L1838) current_plan_doesnt_match;
* an active plan (starts at/before now) -> returned unchanged.

``check_current_plan`` runs unmocked; only the bookings lookup and the
document lookup are stubbed, so the accept/reject decision is real code.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.domains.desktops import desktops as mod

DP = mod.DesktopsProcessed


@pytest.fixture
def env(monkeypatch):
    """Stub the plan lookup and the domain document; tests set both."""
    state = {"plan": [], "desktop": {"tag": False}}
    monkeypatch.setattr(
        mod.BookingsProcessed,
        "get_item_bookings",
        staticmethod(lambda *a, **k: state["plan"]),
    )
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, t, d: state["desktop"])
    )
    return state


class TestCheckCurrentPlanGuards:
    def test_no_plan_deployment_desktop_rejected(self, env):
        env["plan"] = []
        env["desktop"] = {"tag": "dep-1"}
        with pytest.raises(Error) as exc:
            DP.check_current_plan({"user_id": "u-1"}, "d-1")
        assert exc.value.error["description_code"] == "needs_deployment_booking"

    def test_no_plan_standalone_desktop_rejected(self, env):
        env["plan"] = []
        env["desktop"] = {"tag": False}
        with pytest.raises(Error) as exc:
            DP.check_current_plan({"user_id": "u-1"}, "d-1")
        assert exc.value.error["description_code"] == "current_plan_doesnt_match"

    def test_active_plan_is_returned(self, env):
        # A plan already started (start <= now) -> the desktop may run.
        env["plan"] = [
            {"start": "2000-01-01T00:00+0000", "end": "2999-01-01T00:00+0000"}
        ]
        assert DP.check_current_plan({"user_id": "u-1"}, "d-1") == env["plan"]
