#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression pins for the planning boundary-job / integrity fixes.

Three confirmed defects in ``ReservablesPlannerProccess``:

* **A** -- a same-profile *join* rescheduled by deleting EVERY scheduler job on
  the whole physical card (``bookings_reschedule_item_id`` /
  ``bookings_remove_scheduler_item_id`` filter only by ``kwargs.item_id``),
  wiping unrelated plans' boundary jobs, and re-registered none -- so the merged
  window was never re-carved. The reschedule must touch only THIS plan's jobs
  and re-register the merged plan.
* **B** -- ``update_plan`` ignored ``start``/``end`` (re-fed the stored plan to
  ``add_plan``) so it always ``409``-ed on self-overlap, and ran a booking
  deletion before that error. It must apply the requested window, exclude the
  plan from its own overlap check, and delete no bookings.
* **C** -- ``is_any_plan_item_id_overlapped`` computed overlaps then discarded
  them (``log.debug`` only), always returning empty conflicts. It must report
  the overlaps it finds.

Only the rethink layer and sibling collaborators are stubbed; the decisions are
the code's.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.bookings import reservables_planner as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ReservablesPlannerProccess, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ReservablesPlannerProccess),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", tuple(x)))
    monkeypatch.setattr(mod.r, "expr", lambda x: x)
    monkeypatch.setattr(mod.r, "row", MagicMock(name="r.row"))
    monkeypatch.setattr(mod.r, "not_", lambda x: ("NOT", x))

    sched = MagicMock(name="SchedulerHelper")
    for m in (
        "remove_scheduler_startswith_id",
        "bookings_schedule_subitem",
        "bookings_reschedule_item_id",
        "bookings_remove_scheduler_item_id",
    ):
        monkeypatch.setattr(mod.SchedulerHelper, m, getattr(sched, m))
    return {
        "mod": mod,
        "Cls": mod.ReservablesPlannerProccess,
        "router": router,
        "mp": monkeypatch,
        "sched": sched,
    }


def _dt(h):
    return datetime(2027, 1, 1, h, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- A
class TestJoinReschedulePreservesTheCard:
    """A same-profile join must not wipe the whole card, and must re-register
    the merged plan's boundary jobs."""

    def test_join_before_moves_only_this_plans_jobs(self, stub):
        new_plan = {"item_id": "card-1", "start": _dt(9)}
        existing = {
            "id": "plan-existing",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "start": _dt(10),
        }
        stub["Cls"].reschedule_existing_plan_start(new_plan, existing)

        s = stub["sched"]
        # The card-wide wipe must NOT be used any more.
        s.bookings_reschedule_item_id.assert_not_called()
        # Only THIS plan's jobs are removed, then re-registered at the new start.
        s.remove_scheduler_startswith_id.assert_called_once_with("plan-existing")
        s.bookings_schedule_subitem.assert_called_once_with(
            "plan-existing", "gpus", "card-1", "NVIDIA-T4-1Q", _dt(9)
        )

    def test_join_after_keeps_start_anchored_jobs(self, stub):
        # End moved later; a plan's boundary jobs are anchored to its START,
        # which did not change -> nothing is deleted, and the whole-card wipe is
        # never used.
        new_plan = {
            "id": "plan-new",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "end": _dt(13),
        }
        existing = {
            "id": "plan-existing",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "end": _dt(11),
        }
        stub["Cls"].reschedule_existing_plan_end(new_plan, existing)

        s = stub["sched"]
        s.bookings_remove_scheduler_item_id.assert_not_called()
        s.remove_scheduler_startswith_id.assert_not_called()


# --------------------------------------------------------------------------- B
class TestUpdatePlanAppliesDatesAndKeepsBookings:
    def _stored_plan(self, stub, plan):
        rp = stub["router"]("resource_planner")
        rp.get.return_value.run.return_value = plan

    def test_missing_plan_is_not_found(self, stub):
        self._stored_plan(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].update_plan({"user_id": "u"}, "nope", _dt(9), _dt(11))
        assert exc.value.error["error"] == "not_found"

    def test_applies_new_window_reschedules_and_deletes_no_booking(self, stub):
        plan = {
            "id": "plan-1",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "start": _dt(10),
            "end": _dt(12),
        }
        self._stored_plan(stub, plan)
        rp = stub["router"]("resource_planner")
        # The overlap check (ReQL ``<=`` terms) is pinned separately; here we
        # stub it to a no-op to isolate the apply / reschedule / no-delete
        # behaviour.
        stub["mp"].setattr(
            stub["Cls"],
            "check_plan_item_id_overlapped",
            classmethod(lambda cls, candidate, exclude_plan_id=None: None),
        )
        # No booking falls out of the EXPANDED window.
        bk = stub["router"]("bookings")
        bk.filter.return_value.filter.return_value.run.return_value = []

        returned = stub["Cls"].update_plan(
            {"user_id": "u", "role_id": "admin"},
            "plan-1",
            "2027-01-01T09:00:00+00:00",  # ISO strings, as the route forwards
            "2027-01-01T14:00:00+00:00",
        )
        assert returned == "plan-1"

        # The stored row is updated to the requested (rounded) window...
        upd = rp.get.return_value.update.call_args_list
        assert upd, "resource_planner row was never updated"
        written = upd[-1].args[0]
        assert written["start"] == _dt(9)
        assert written["end"].hour == 13 and written["end"].minute == 59

        # ...this plan's boundary jobs move to the new start...
        s = stub["sched"]
        s.remove_scheduler_startswith_id.assert_called_once_with("plan-1")
        assert s.bookings_schedule_subitem.call_args.args[0] == "plan-1"

        # ...and NO booking is deleted (the bookings table is never touched).
        bk = stub["router"]("bookings")
        bk.get_all.return_value.delete.assert_not_called()
        bk.filter.return_value.delete.assert_not_called()

    def test_shrink_deletes_only_fallen_out_and_resets_domain(self, stub):
        # Shrinking a window keeps the intended refit: a booking that no longer
        # fits is deleted and its domain's booking_id reset -- but only after the
        # (successful) validation + apply, never before an error.
        plan = {
            "id": "plan-1",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "start": _dt(10),
            "end": _dt(14),
        }
        self._stored_plan(stub, plan)
        stub["mp"].setattr(
            stub["Cls"],
            "check_plan_item_id_overlapped",
            classmethod(lambda cls, candidate, exclude_plan_id=None: None),
        )
        bk = stub["router"]("bookings")
        bk.filter.return_value.filter.return_value.run.return_value = [
            {
                "id": "bk-out",
                "item_type": "desktop",
                "item_id": "d1",
                "start": _dt(10),
                "end": _dt(16),
            }
        ]
        stub["Cls"].update_plan({"user_id": "u"}, "plan-1", _dt(11), _dt(13))

        bk.get_all.assert_called_once_with(("ARGS", ("bk-out",)), index="id")
        bk.get_all.return_value.delete.assert_called_once()
        dom = stub["router"]("domains")
        resets = [c.args[0] for c in dom.get.return_value.update.call_args_list]
        assert {"booking_id": False} in resets
        dom.get.assert_any_call("d1")

    def test_self_overlap_is_excluded_from_the_check(self, stub):
        # The plan's own still-stored row must not count as an overlap.
        plan = {
            "id": "plan-1",
            "item_type": "gpus",
            "item_id": "card-1",
            "subitem_id": "NVIDIA-T4-1Q",
            "start": _dt(10),
            "end": _dt(12),
        }
        self._stored_plan(stub, plan)
        seen = {}

        def fake_check(cls, candidate, exclude_plan_id=None):
            seen["exclude"] = exclude_plan_id

        stub["mp"].setattr(
            stub["Cls"], "check_plan_item_id_overlapped", classmethod(fake_check)
        )
        stub["router"](
            "bookings"
        ).filter.return_value.filter.return_value.run.return_value = []
        stub["Cls"].update_plan({"user_id": "u"}, "plan-1", _dt(9), _dt(11))
        assert seen.get("exclude") == "plan-1"


# --------------------------------------------------------------------------- C
class TestCheckIntegrityReportsOverlaps:
    def test_overlap_is_reported_not_swallowed(self, stub):
        rp = stub["router"]("resource_planner")
        # First query: all plans.
        rp.run.return_value = [
            {
                "id": "p-a",
                "item_id": "card-1",
                "start": _dt(10),
                "end": _dt(14),
            }
        ]
        # Overlap sub-queries (get_all->filter->filter->run): a second plan
        # overlaps card-1.
        overlap = [{"id": "p-b", "item_id": "card-1", "start": _dt(12), "end": _dt(16)}]
        rp.get_all.return_value.filter.return_value.filter.return_value.run.return_value = (
            overlap
        )

        conflicts = stub["Cls"].is_any_plan_item_id_overlapped()

        # The card with a real overlap is reported with a non-empty list naming
        # the offending plan -- the previous code returned all-empty lists.
        assert "card-1" in conflicts
        entry = conflicts["card-1"]
        assert entry["start"] or entry["end"]
        reported = [o["overlaps"] for o in entry["start"] + entry["end"]]
        assert "p-b" in reported

    def test_clean_planner_reports_nothing(self, stub):
        rp = stub["router"]("resource_planner")
        rp.run.return_value = [
            {"id": "p-a", "item_id": "card-1", "start": _dt(10), "end": _dt(11)}
        ]
        rp.get_all.return_value.filter.return_value.filter.return_value.run.return_value = (
            []
        )
        assert stub["Cls"].is_any_plan_item_id_overlapped() == {}
