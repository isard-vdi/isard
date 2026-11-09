# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which problems a disk has, which fix answers each, and which fixes are costly."""

import pytest
from isardvdi_common.lib.storage import actions as disk_actions
from isardvdi_common.lib.storage import problems as p
from isardvdi_common.models.storage import PENDING_ACTIONS


def _found(row):
    return [(problem.code, problem.fix) for problem in p.diagnose(row)]


@pytest.mark.parametrize(
    "row, found",
    [
        ({"status": "ready"}, []),
        ({"status": "maintenance"}, [("storage_busy", None)]),
        (
            {"status": "damaged"},
            [("storage_damaged", "check"), ("storage_damaged", "repair_all")],
        ),
        ({"status": "broken_chain"}, [("storage_broken_chain", "check_backing_chain")]),
        ({"status": "orphan"}, [("storage_unavailable", None)]),
        (
            {"status": "ready", "pending_actions": {"repair_leaks": {}}},
            [("storage_leaks", "repair_leaks")],
        ),
        (
            {"status": "damaged", "pending_actions": {"repair_leaks": {}}},
            [("storage_damaged", "repair_all"), ("storage_leaks", "repair_leaks")],
        ),
        (
            {"status": "ready", "pending_actions": {"dig_holes": {}, "remeasure": {}}},
            [("storage_zeros", "dig_holes")],
        ),
        (
            {
                "status": "ready",
                "pending_actions": {"check_integrity": {}, "check_inconclusive": {}},
            },
            [("storage_check_due", "check")],
        ),
        (
            {
                "status": "ready",
                "pending_actions": {"repair_leaks": {}, "review_damage": {}},
            },
            [("storage_review_damage", None), ("storage_leaks", "repair_leaks")],
        ),
    ],
)
def test_diagnose(row, found):
    assert _found(row) == found


@pytest.mark.parametrize(
    "fix, costly",
    [
        ("check", False),
        ("check_backing_chain", False),
        ("repair_leaks", False),
        ("repair_all", True),
        ("dig_holes", True),
        ("sparsify", True),
    ],
)
def test_the_cost_of_each_fix_comes_from_the_registry(fix, costly):
    assert p.is_costly(fix) is costly


@pytest.mark.parametrize(
    "action, what, costly",
    [
        ("dig_holes", None, True),
        ("sparsify", None, True),
        ("convert", None, True),
        ("recreate", None, True),
        ("repair", "all", True),
        ("repair", "leaks", False),
        ("check_integrity", None, False),
        ("check_backing_chain", None, False),
        ("resize", None, False),
        ("an_unknown_label", None, False),
    ],
)
def test_the_registry_says_which_actions_are_costly(action, what, costly):
    assert disk_actions.is_costly(action, what) is costly


def test_a_busy_disk_is_waited_for_and_an_unfixable_one_left_to_an_admin():
    assert p.mode(p.Problem("storage_busy", None, True)) == "wait"
    assert p.mode(p.PENDING_PROBLEMS["review_damage"]) == "admin"
    assert p.mode(p.PENDING_PROBLEMS["repair_leaks"]) == "quick"
    assert p.mode(p.PENDING_PROBLEMS["dig_holes"]) == "costly"


def test_every_fix_and_mark_is_declared():
    named = {
        problem.fix
        for problem in [
            *(x for v in p.STATUS_PROBLEMS.values() for x in v),
            *p.PENDING_PROBLEMS.values(),
        ]
        if problem.fix
    }
    assert named <= set(p.FIXES)
    assert set(p.QUICK_ORDER) == {f for f in p.FIXES if not p.is_costly(f)}
    for fix in p.FIXES.values():
        assert fix["action"] in disk_actions.DISK_ACTIONS
        assert fix["mark"] is None or fix["mark"] in PENDING_ACTIONS


def test_the_interactive_origin_is_declared_on_every_mark_it_records():
    for fix in p.QUICK_ORDER:
        mark = p.FIXES[fix]["mark"]
        if mark:
            assert p.FOUND_BY_INTERACTIVE in PENDING_ACTIONS[mark]["flagged_by"]
