#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive plan/booking removal paths of ``ReservablesPlannerProccess``.

Deleting a plan or a card's availability removes ``resource_planner`` rows and
bookings and resets the domains that pointed at them -- irreversible writes.
These pin, on the real functions:

* ``delete_plan`` -- refuses a missing plan (``not_found``) before doing
  anything, and on success resets ``booking_id`` on the referencing
  desktop / deployment domains.
* ``delete_card_subitem_plans`` -- deletes only this card's phantom plans; a
  single-card booking is deleted and its domain reset, a multi-card booking is
  trimmed (kept) instead.
* ``delete_item`` -- after processing its subitems it deletes the GPU card row.

Only the rethink layer and the sibling collaborators (``ResourcePlanner``,
``SchedulerHelper``, ``reservables``) are stubbed; the decisions are the code's.
What must NOT be written is asserted alongside what is.
"""

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
    # Scheduler side effects are irrelevant to the DB decisions.
    sched = MagicMock(name="SchedulerHelper")
    monkeypatch.setattr(mod.SchedulerHelper, "remove_scheduler_startswith_id", sched)
    return {
        "mod": mod,
        "Cls": mod.ReservablesPlannerProccess,
        "router": router,
        "mp": monkeypatch,
        "sched": sched,
    }


def _dom_updates(stub):
    dom = stub["router"]("domains")
    direct = [c.args[0] for c in dom.get.return_value.update.call_args_list]
    by_tag = [c.args[0] for c in dom.get_all.return_value.update.call_args_list]
    return direct, by_tag


class TestDeletePlan:
    def _rp(self, stub, deleted, changes=None):
        mod = stub["mod"]
        stub["mp"].setattr(
            mod.ResourcePlanner,
            "delete_plan_by_id",
            classmethod(lambda cls, pid: {"deleted": deleted}),
        )
        stub["mp"].setattr(
            mod.ResourcePlanner,
            "delete_bookings_by_plan_id",
            classmethod(lambda cls, pid: {"changes": changes or []}),
        )

    def test_missing_plan_refused_before_any_work(self, stub):
        self._rp(stub, deleted=0)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].delete_plan("nope")
        assert exc.value.error["error"] == "not_found"
        # Nothing further happened: no scheduler cleanup, no domain writes.
        stub["sched"].assert_not_called()
        assert _dom_updates(stub) == ([], [])

    def test_desktop_booking_id_reset_on_success(self, stub):
        self._rp(
            stub,
            deleted=1,
            changes=[
                {"old_val": {"id": "b1", "item_type": "desktop", "item_id": "d1"}}
            ],
        )
        stub["Cls"].delete_plan("p1")
        direct, by_tag = _dom_updates(stub)
        assert {"booking_id": False} in direct
        stub["router"]("domains").get.assert_any_call("d1")
        assert by_tag == []  # a desktop is reset by id, not by the tag index

    def test_deployment_booking_id_reset_by_tag(self, stub):
        self._rp(
            stub,
            deleted=1,
            changes=[
                {"old_val": {"id": "b1", "item_type": "deployment", "item_id": "dep1"}}
            ],
        )
        stub["Cls"].delete_plan("p1")
        direct, by_tag = _dom_updates(stub)
        assert {"booking_id": False} in by_tag
        stub["router"]("domains").get_all.assert_any_call("dep1", index="tag")


class TestDeleteCardSubitemPlans:
    def _plans(self, stub, plan_ids):
        rp = stub["router"]("resource_planner")
        rp.get_all.return_value.__getitem__.return_value.run.return_value = plan_ids

    def _bookings(self, stub, bookings):
        stub["router"]("bookings").filter.return_value.run.return_value = bookings

    def test_no_plans_is_noop(self, stub):
        self._plans(stub, [])
        assert stub["Cls"].delete_card_subitem_plans("card-1", "1Q") == (0, 0)
        # No plan deletion, no booking scan.
        stub["router"](
            "resource_planner"
        ).get_all.return_value.delete.assert_not_called()

    def test_single_card_booking_deleted_and_domain_reset(self, stub):
        self._plans(stub, ["p1"])
        self._bookings(
            stub,
            [
                {
                    "id": "b1",
                    "plans": [{"plan_id": "p1"}],
                    "item_type": "desktop",
                    "item_id": "d1",
                }
            ],
        )
        plans_deleted, bookings_deleted = stub["Cls"].delete_card_subitem_plans(
            "card-1", "1Q"
        )
        assert (plans_deleted, bookings_deleted) == (1, 1)
        bk = stub["router"]("bookings")
        bk.get.return_value.delete.assert_called_once()
        # The now-danging desktop is reset...
        direct, _ = _dom_updates(stub)
        assert {"booking_id": False} in direct
        # ...and the emptied booking is NOT merely trimmed.
        bk.get.return_value.update.assert_not_called()

    def test_multi_card_booking_is_trimmed_not_deleted(self, stub):
        self._plans(stub, ["p1"])
        self._bookings(
            stub,
            [
                {
                    "id": "b1",
                    "plans": [{"plan_id": "p1"}, {"plan_id": "pX"}],
                    "item_type": "deployment",
                    "item_id": "dep1",
                }
            ],
        )
        plans_deleted, bookings_deleted = stub["Cls"].delete_card_subitem_plans(
            "card-1", "1Q"
        )
        assert (plans_deleted, bookings_deleted) == (1, 0)
        bk = stub["router"]("bookings")
        # Surviving card kept: booking trimmed to the remaining plan...
        bk.get.return_value.update.assert_called_once_with(
            {"plans": [{"plan_id": "pX"}]}
        )
        # ...and NOT deleted.
        bk.get.return_value.delete.assert_not_called()


class TestDeleteItem:
    def test_deletes_card_row_after_processing_subitems(self, stub):
        deleted_sub = MagicMock(name="delete_subitem")
        stub["mp"].setattr(
            stub["Cls"],
            "delete_subitem",
            classmethod(lambda cls, it, iid, sid, data=None: deleted_sub(sid)),
        )
        enable = MagicMock(name="enable_subitems")
        stub["mp"].setattr(
            stub["Cls"].reservables,
            "enable_subitems",
            lambda *a, **k: enable(*a),
        )

        stub["Cls"].delete_item("gpus", "card-1", subitems=["1Q", "2Q"])

        # Every subitem processed, then the physical card row is removed.
        assert deleted_sub.call_args_list[0].args[0] == "1Q"
        assert deleted_sub.call_args_list[1].args[0] == "2Q"
        gpus = stub["router"]("gpus")
        gpus.get.assert_any_call("card-1")
        gpus.get.return_value.delete.assert_called_once()
