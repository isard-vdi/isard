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
