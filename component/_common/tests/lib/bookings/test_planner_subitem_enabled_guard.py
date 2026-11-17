#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``add_plan`` must refuse a profile the card does not have enabled."""

import datetime

import pytest


class _Reservables:
    """Stub of the ``Reservables`` facade: only the enablement lookup matters."""

    def __init__(self, enabled):
        self._enabled = enabled

    def list_subitems_enabled(self, item_type, item_id):
        return [{"id": i} for i in self._enabled]


def _data(subitem_id):
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "item_type": "gpus",
        "item_id": "card1",
        "subitem_id": subitem_id,
        "start": now + datetime.timedelta(days=1),
        "end": now + datetime.timedelta(days=1, hours=2),
    }


@pytest.fixture
def planner(monkeypatch):
    from isardvdi_common.lib.bookings import reservables_planner as mod

    monkeypatch.setattr(
        mod.ReservablesPlannerProccess,
        "reservables",
        _Reservables(["NVIDIA-TESTCARD-4Q"]),
    )
    return mod


class TestSubitemEnabledGuard:
    def test_guard_raises_for_a_profile_the_card_does_not_enable(self, planner):
        from isardvdi_common.helpers.error_factory import Error

        with pytest.raises(Error) as excinfo:
            planner.ReservablesPlannerProccess._assert_subitem_enabled(
                "gpus", "card1", "NVIDIA-TESTCARD-8Q"
            )
        assert excinfo.value.error["description_code"] == "subitem_not_enabled_on_item"

    def test_guard_passes_for_an_enabled_profile(self, planner):
        planner.ReservablesPlannerProccess._assert_subitem_enabled(
            "gpus", "card1", "NVIDIA-TESTCARD-4Q"
        )

    def test_add_plan_refuses_before_writing_anything(self, planner):
        from isardvdi_common.helpers.error_factory import Error

        with pytest.raises(Error) as excinfo:
            planner.ReservablesPlannerProccess.add_plan(
                {"user_id": "u-admin", "role_id": "admin"},
                _data("NVIDIA-TESTCARD-8Q"),
            )
        assert excinfo.value.error["description_code"] == "subitem_not_enabled_on_item"
