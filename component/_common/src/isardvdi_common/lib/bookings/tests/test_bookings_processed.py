# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``BookingsProcessed`` — pins the Bug 33 remediation.

Bug 33 (load-testing rev 8): ``GET /api/v4/items/bookings/gpu`` returned
500 "Failed to retrieve GPU bookings forecast." regardless of the
booking table state. The load-testing report misdiagnosed it as a
response-model mismatch in the ``.group/.ungroup`` ReQL pipeline.
The actual root cause was simpler: ``bookings_max_units`` was
decorated with ``@classmethod`` but its body had a single positional
parameter ``bookings`` — no ``cls``. Every call from
``get_booking_profile_count_within_one_hour`` (three sites) tried to
pass two positional args to a one-arg signature and crashed with
``TypeError: bookings_max_units() takes 1 positional argument but 2
were given``. The route's ``except Exception`` swallowed the
TypeError into a generic 500.

The fix changes the decorator to ``@staticmethod`` since the function
operates only on its argument.
"""

import inspect
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.bookings.bookings import BookingsProcessed


class TestBookingsMaxUnits:
    def test_can_be_called_off_class(self):
        """The smoking gun — calling the method off the class with one
        positional arg must NOT raise TypeError. Before the fix,
        ``BookingsProcessed.bookings_max_units([])`` raised because
        the @classmethod decorator passed ``BookingsProcessed`` as the
        implicit first arg AND the test passed a list, totalling two
        args to a one-arg signature.
        """
        # If the decorator is @classmethod, this would crash. With
        # @staticmethod it's a plain call.
        result = BookingsProcessed.bookings_max_units([])
        assert result == 0

    def test_returns_zero_for_empty_input(self):
        assert BookingsProcessed.bookings_max_units([]) == 0

    def test_decorator_is_staticmethod_not_classmethod(self):
        """Pin the fix at the introspection level: the wrapper attached
        to the class must be a ``staticmethod``, not a ``classmethod``.

        Catches a future revert that "tidies up" by re-adding
        ``@classmethod``, which would silently re-introduce Bug 33.
        """
        # ``inspect.getattr_static`` returns the descriptor (not the
        # bound method), so we can check its underlying type directly.
        descriptor = inspect.getattr_static(BookingsProcessed, "bookings_max_units")
        assert isinstance(descriptor, staticmethod), (
            f"bookings_max_units must be @staticmethod; got "
            f"{type(descriptor).__name__}. See Bug 33."
        )

    def test_returns_max_units_for_single_booking(self):
        """A single booking returns its own units count (the function
        joins overlapping intervals via the ``portion`` library and
        returns the max units across all atomic interval slices)."""
        bookings = [{"id": "b1", "start": 0, "end": 100, "units": 3}]
        assert BookingsProcessed.bookings_max_units(bookings) == 3

    def test_sums_units_across_overlapping_bookings(self):
        """Two bookings overlapping in [50, 100] sum to 5 units in the
        overlap and 2 / 3 outside. The function returns the max (5).
        Pins the contract the route depends on for forecasting GPU
        capacity 30/60 minutes ahead.
        """
        bookings = [
            {"id": "b1", "start": 0, "end": 100, "units": 2},
            {"id": "b2", "start": 50, "end": 200, "units": 3},
        ]
        assert BookingsProcessed.bookings_max_units(bookings) == 5


# Helpers shared by booking-update tests
def _make_booking(start_h=11, end_h=12):
    return {
        "id": "b1",
        "item_id": "d1",
        "item_type": "desktop",
        "reservables": {"vgpus": ["NVIDIA-A40-1Q"]},
        "units": 1,
        "start": datetime(2026, 5, 1, start_h, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 5, 1, end_h, 0, tzinfo=timezone.utc),
    }


class TestExistingBookingUpdateFits:
    """Pin Bug 1 remediation — ``existing_booking_update_fits`` was
    stubbed to ``return False`` during the apiv3 → apiv4 port. Every
    call to ``PUT /item/booking/event/{id}/edit`` raised
    409 ``booking_does_not_fit_date`` regardless of input. The fix
    restores the real interval-fit check using
    ``ReservablesPlannerCompute`` class methods.
    """

    def test_not_a_constant_return_false(self):
        """Source-level guard against future re-stubbing. The function
        body must mention ``booking_provisioning`` — i.e. it must
        actually run the planner check.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        src = inspect.getsource(ReservablesPlannerProccess.existing_booking_update_fits)
        assert "booking_provisioning" in src, (
            "existing_booking_update_fits must call booking_provisioning; "
            "Bug 1 stub regression"
        )
        # First non-decorator, non-docstring statement must not be a literal
        # ``return False``. (Catches the original stub shape.)
        body_lines = [
            ln.strip()
            for ln in src.splitlines()
            if ln.strip()
            and not ln.strip().startswith("#")
            and not ln.strip().startswith('"')
            and not ln.strip().startswith("def ")
            and not ln.strip().startswith("@")
        ]
        assert body_lines and body_lines[0] != "return False", (
            "first statement must not be unconditional ``return False`` — "
            "that was the Bug 1 stub"
        )

    def test_signature_accepts_new_dates(self):
        """The fix extends the API to take ``new_start`` / ``new_end``
        so booking updates can validate the new window, not just the
        booking's stored dates. Pins the kwargs in the signature.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        sig = inspect.signature(ReservablesPlannerProccess.existing_booking_update_fits)
        assert "new_start" in sig.parameters
        assert "new_end" in sig.parameters

    def test_returns_true_when_one_plan_contains_window(self, monkeypatch):
        """Happy path — one plan covers the booking interval, function
        returns True. Mocks ``ReservablesPlannerCompute`` class methods
        so we don't hit RethinkDB.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )
        from isardvdi_common.lib.bookings.reservables_planner_compute import (
            ReservablesPlannerCompute,
        )

        plan_start = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
        plan_end = datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc)
        booking = _make_booking(start_h=11, end_h=12)

        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "payload_priority",
            classmethod(
                lambda cls, payload, reservables: {
                    "priority": {"NVIDIA-A40-1Q": 50},
                    "forbid_time": 0,
                    "max_time": 720,
                    "max_items": 10,
                }
            ),
        )
        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "booking_provisioning",
            classmethod(
                lambda cls, *a, **kw: [
                    {
                        "id": "p1",
                        "start": plan_start,
                        "end": plan_end,
                        "units": 5,
                        "event_type": "available",
                    }
                ]
            ),
        )

        assert (
            ReservablesPlannerProccess.existing_booking_update_fits(
                payload={"user_id": "u1"}, booking=booking
            )
            is True
        )

    def test_returns_false_when_no_plan_covers_window(self, monkeypatch):
        """Collision path — no available plan contains the booking's
        window, function returns False.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )
        from isardvdi_common.lib.bookings.reservables_planner_compute import (
            ReservablesPlannerCompute,
        )

        booking = _make_booking(start_h=11, end_h=12)

        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "payload_priority",
            classmethod(lambda cls, payload, reservables: {"priority": {}}),
        )
        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "booking_provisioning",
            classmethod(lambda cls, *a, **kw: []),
        )

        assert (
            ReservablesPlannerProccess.existing_booking_update_fits(
                payload={"user_id": "u1"}, booking=booking
            )
            is False
        )

    def test_uses_new_dates_when_provided(self, monkeypatch):
        """When ``new_start`` / ``new_end`` are passed, the validation
        runs against THOSE dates, not the booking's stored ones. This
        is the apiv3 semantic gap the apiv4 port closes — main never
        validated the new window during update.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )
        from isardvdi_common.lib.bookings.reservables_planner_compute import (
            ReservablesPlannerCompute,
        )

        booking = _make_booking(start_h=11, end_h=12)
        # Move the booking to 9:00-10:00, which is OUTSIDE the available plan
        new_start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        new_end = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)

        captured_dates = {}

        def fake_provisioning(cls, *args, **kwargs):
            # Positional: payload, item_type, item_id, reservables, units, priority, fromDate, toDate
            captured_dates["fromDate"] = args[6]
            captured_dates["toDate"] = args[7]
            return [
                {
                    "id": "p1",
                    "start": datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
                    "end": datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
                    "units": 5,
                    "event_type": "available",
                }
            ]

        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "payload_priority",
            classmethod(lambda cls, payload, reservables: {"priority": {}}),
        )
        monkeypatch.setattr(
            ReservablesPlannerCompute,
            "booking_provisioning",
            classmethod(fake_provisioning),
        )

        result = ReservablesPlannerProccess.existing_booking_update_fits(
            payload={"user_id": "u1"},
            booking=booking,
            new_start=new_start,
            new_end=new_end,
        )
        # The new window 9-10 doesn't fit inside the 11-14 plan
        assert result is False
        # And the dates passed to booking_provisioning were the new ones
        assert captured_dates["fromDate"] == new_start
        assert captured_dates["toDate"] == new_end


class TestBookingsUpdate:
    """End-to-end test of ``BookingsProcessed.update`` flow — pins both
    Bug 1 (the underlying fits check) and the not-found path.
    """

    @pytest.fixture
    def update_stub(self, monkeypatch):
        from isardvdi_common.lib.bookings import bookings as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            mod.BookingsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.BookingsProcessed),
            "_rdb_connection",
            property(lambda self: MagicMock(name="conn")),
        )
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(mod.r, "table", mock_table)
        return {"mod": mod, "mock_table": mock_table}

    def test_raises_when_booking_not_found(self, update_stub):
        from isardvdi_common.helpers.error_base import ErrorBase

        update_stub["mock_table"].return_value.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            update_stub["mod"].BookingsProcessed.update(
                booking_id="missing",
                payload={"user_id": "u1"},
                title="x",
                start="2026-05-01T10:00+0000",
                end="2026-05-01T11:00+0000",
            )

    def test_raises_conflict_when_fits_returns_false(self, update_stub, monkeypatch):
        from isardvdi_common.helpers.error_base import ErrorBase
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        update_stub["mock_table"].return_value.get.return_value.run.return_value = (
            _make_booking()
        )
        monkeypatch.setattr(
            ReservablesPlannerProccess,
            "existing_booking_update_fits",
            classmethod(lambda cls, *a, **kw: False),
        )
        with pytest.raises(ErrorBase):
            update_stub["mod"].BookingsProcessed.update(
                booking_id="b1",
                payload={"user_id": "u1"},
                title="renamed",
                start="2026-05-01T11:00+0000",
                end="2026-05-01T12:00+0000",
            )

    def test_updates_when_fits_returns_true(self, update_stub, monkeypatch):
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        update_stub["mock_table"].return_value.get.return_value.run.return_value = (
            _make_booking()
        )
        monkeypatch.setattr(
            ReservablesPlannerProccess,
            "existing_booking_update_fits",
            classmethod(lambda cls, *a, **kw: True),
        )
        update_stub["mod"].BookingsProcessed.update(
            booking_id="b1",
            payload={"user_id": "u1"},
            title="renamed",
            start="2026-05-01T11:00+0000",
            end="2026-05-01T12:00+0000",
        )
        # Assert the update payload reached r.table("bookings").get("b1").update(...)
        update_chain = update_stub["mock_table"].return_value.get.return_value.update
        update_chain.assert_called()
        call_payload = update_chain.call_args.args[0]
        assert call_payload["title"] == "renamed"
        # start/end were converted to tz-aware datetime
        assert call_payload["start"] == datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
        assert call_payload["end"] == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    def test_passes_new_dates_to_fits_check(self, update_stub, monkeypatch):
        """``BookingsProcessed.update`` must forward ``new_start`` and
        ``new_end`` to ``existing_booking_update_fits`` so the planner
        check happens against the requested window, not the stored one.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        update_stub["mock_table"].return_value.get.return_value.run.return_value = (
            _make_booking()
        )

        captured = {}

        def fake_fits(cls, payload, booking, new_start=None, new_end=None):
            captured["new_start"] = new_start
            captured["new_end"] = new_end
            return True

        monkeypatch.setattr(
            ReservablesPlannerProccess,
            "existing_booking_update_fits",
            classmethod(fake_fits),
        )
        update_stub["mod"].BookingsProcessed.update(
            booking_id="b1",
            payload={"user_id": "u1"},
            title="renamed",
            start="2026-05-01T13:00+0000",
            end="2026-05-01T15:00+0000",
        )
        assert captured["new_start"] == datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
        assert captured["new_end"] == datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
