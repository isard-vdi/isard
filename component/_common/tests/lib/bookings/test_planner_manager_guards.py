"""Unit tests for the GPU planner manager-ownership guards.

The two guards are ``@classmethod``s of ``ReservablesPlannerProccess``; the
tests bind their underlying functions to a minimal stand-in receiver so the
``cls.reservables`` lookup and the rdb context can be faked without a DB. This
pins the category-delegation authorization model:

- ``_assert_manager_owns_card``: admin passes; a manager passes only on a card
  whose ``gpus.category`` equals the manager's category (a global/None card is
  forbidden for a manager).
- ``_assert_manager_owns_plan``: a missing plan is ``not_found``; a cross-category
  plan's ``forbidden`` is COLLAPSED to ``not_found`` so a manager cannot
  enumerate other categories' plan ids by probing.
"""

import contextlib
from unittest import mock

from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.bookings import reservables_planner
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess


class _Table:
    def __init__(self, row):
        self._row = row

    def get(self, _id):
        return self

    def run(self, _conn):
        return self._row


class _R:
    def __init__(self, row):
        self._row = row

    def table(self, _name):
        return _Table(self._row)


class _Reservables:
    def __init__(self, category):
        self._category = category

    def get_item_category(self, _item_type, _item_id):
        return self._category


class _Self:
    """Minimal stand-in for the planner instance the guards are bound to."""

    def __init__(self, card_category):
        self.reservables = _Reservables(card_category)
        self._rdb_connection = None

    def _rdb_context(self):
        return contextlib.nullcontext()

    # The guards are classmethods; ``__func__`` unwraps them so they bind to
    # this stand-in (cls resolves to the harness object).
    _assert_manager_owns_card = (
        ReservablesPlannerProccess._assert_manager_owns_card.__func__
    )
    _assert_manager_owns_plan = (
        ReservablesPlannerProccess._assert_manager_owns_plan.__func__
    )


def _payload(role, category="catA"):
    return {"role_id": role, "category_id": category}


def _raises(fn):
    try:
        fn()
    except Error as e:
        return e.error["error"]
    return None  # no error raised


# --- _assert_manager_owns_card ----------------------------------------------


def test_admin_passes_any_card():
    s = _Self(card_category="catB")
    assert _raises(lambda: s._assert_manager_owns_card(_payload("admin"), "c")) is None


def test_manager_passes_own_category_card():
    s = _Self(card_category="catA")
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        is None
    )


def test_manager_forbidden_on_other_category_card():
    s = _Self(card_category="catB")
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        == "forbidden"
    )


def test_manager_forbidden_on_global_card():
    # A non-delegated (None) card is admin-only — forbidden for a manager.
    s = _Self(card_category=None)
    assert (
        _raises(lambda: s._assert_manager_owns_card(_payload("manager", "catA"), "c"))
        == "forbidden"
    )


# --- _assert_manager_owns_plan (403 -> 404 collapse) ------------------------


def _owns_plan(plan_row, card_category, payload):
    s = _Self(card_category)
    # the guard reads r.table(...).get(plan_id).run(...)
    with mock.patch.object(reservables_planner, "r", _R(plan_row)):
        return _raises(lambda: s._assert_manager_owns_plan(payload, "plan-id"))


def test_admin_passes_any_plan():
    assert _owns_plan({"item_id": "c"}, "catB", _payload("admin")) is None


def test_missing_plan_is_not_found():
    assert _owns_plan(None, "catA", _payload("manager", "catA")) == "not_found"


def test_cross_category_plan_collapses_403_to_404():
    # Manager probes a plan on a card delegated to ANOTHER category: the guard
    # must hide it as not_found, never leak a 403 that confirms it exists.
    assert (
        _owns_plan({"item_id": "c"}, "catB", _payload("manager", "catA")) == "not_found"
    )


def test_manager_own_category_plan_passes():
    assert _owns_plan({"item_id": "c"}, "catA", _payload("manager", "catA")) is None
