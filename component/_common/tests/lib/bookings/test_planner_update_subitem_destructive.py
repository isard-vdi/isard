#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Remaining destructive paths of ``ReservablesPlannerProccess``.

* ``delete_subitem`` -- last card → deassign desktops and delete every plan;
  non-last card → surgically detach this card's plans only (no deassign).

``update_plan``'s refit/reschedule behaviour lives in
``test_planner_boundary_jobs.py``.

Only rethink and the sibling collaborators are stubbed; the decisions are the
code's. What must NOT be removed is asserted alongside what is.
"""

from unittest.mock import MagicMock

import pytest


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

    # r.row: a ReQL expr stand-in that swallows getitem/contains/comparisons
    # (a plain MagicMock returns NotImplemented for ``<=`` and would TypeError).
    class _Row:
        def __getitem__(self, k):
            return self

        def contains(self, *a, **k):
            return self

        def __le__(self, o):
            return self

        def __ge__(self, o):
            return self

        def __lt__(self, o):
            return self

        def __gt__(self, o):
            return self

        def __and__(self, o):
            return self

        def __or__(self, o):
            return self

    monkeypatch.setattr(mod.r, "row", _Row())
    return {
        "mod": mod,
        "Cls": mod.ReservablesPlannerProccess,
        "router": router,
        "mp": monkeypatch,
    }


class TestDeleteSubitem:
    def _spies(self, stub):
        deassign = MagicMock(name="deassign_desktops")
        stub["mp"].setattr(
            stub["Cls"].reservables,
            "deassign_desktops_with_gpu",
            lambda *a, **k: deassign(*a),
        )
        del_plan = MagicMock(name="delete_plan")
        stub["mp"].setattr(
            stub["Cls"], "delete_plan", classmethod(lambda cls, pid: del_plan(pid))
        )
        del_card = MagicMock(name="delete_card_subitem_plans", return_value=(0, 0))
        stub["mp"].setattr(
            stub["Cls"],
            "delete_card_subitem_plans",
            classmethod(lambda cls, iid, sid: del_card(iid, sid)),
        )
        return deassign, del_plan, del_card

    def test_last_card_deassigns_and_deletes_all_plans(self, stub):
        deassign, del_plan, del_card = self._spies(stub)
        data = {"last": [True], "deployments": [], "plans": [{"id": "p1"}]}
        stub["Cls"].delete_subitem("gpus", "card-1", "NVIDIA-A40-1Q", data)
        deassign.assert_called_once_with("gpus", "NVIDIA-A40-1Q", None)
        del_plan.assert_called_once_with("p1")
        # The surgical non-last path must NOT run for a last-card disable.
        del_card.assert_not_called()

    def test_non_last_card_detaches_only_this_cards_plans(self, stub):
        deassign, del_plan, del_card = self._spies(stub)
        data = {"last": [False], "deployments": [], "plans": [{"id": "p1"}]}
        stub["Cls"].delete_subitem("gpus", "card-1", "NVIDIA-A40-1Q", data)
        del_card.assert_called_once_with("card-1", "NVIDIA-A40-1Q")
        # Desktops keep their GPU: no broad deassign, no full plan deletion.
        deassign.assert_not_called()
        del_plan.assert_not_called()
