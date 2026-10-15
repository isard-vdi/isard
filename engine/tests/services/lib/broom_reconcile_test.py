"""Which rows the broom settles, and on which evidence it refuses to."""

from unittest.mock import MagicMock

import pytest

from engine.services.lib.broom_reconcile import (
    STATUSES_NEVER_REAPED,
    AbsenceTracker,
    IdlePausedTracker,
    vcpu_seconds,
)

ONLINE = ["hyp-1", "hyp-2"]
NOT_HELD = lambda domain_id: False


def _row(domain_id, status, hyp_started=False):
    return {"id": domain_id, "status": status, "hyp_started": hyp_started}


def _listings(**by_hyp):
    listings = {hyp: {} for hyp in ONLINE}
    for hyp, domains in by_hyp.items():
        listings[hyp.replace("_", "-")] = {
            d: {"status": "Started", "detail": ""} for d in domains
        }
    return listings


def _passes(tracker, rows, listings, n, online=ONLINE, is_held=NOT_HELD):
    due = []
    for _ in range(n):
        due = tracker.absent(rows, online, listings, is_held)
    return [r["id"] for r in due]


class TestAbsence:
    @pytest.mark.parametrize(
        "row",
        [
            _row("d-1", "Unknown"),
            _row("d-1", "Unknown", "hyp-1"),
            _row("d-1", "Started", "hyp-2"),
            _row("d-1", "Paused", "hyp-1"),
        ],
    )
    def test_a_row_no_online_hypervisor_runs_is_due_on_the_second_pass(self, row):
        tracker = AbsenceTracker()

        assert _passes(tracker, [row], _listings(), 1) == []
        assert _passes(tracker, [row], _listings(), 1) == ["d-1"]

    def test_a_row_any_hypervisor_runs_is_not_due(self):
        rows = [_row("d-1", "Unknown"), _row("d-2", "Started", "hyp-1")]

        assert _passes(AbsenceTracker(), rows, _listings(hyp_2=["d-1", "d-2"]), 3) == []

    def test_nothing_is_due_while_one_online_hypervisor_has_no_listing(self):
        listings = _listings()
        del listings["hyp-2"]

        assert _passes(AbsenceTracker(), [_row("d-1", "Unknown")], listings, 5) == []

    def test_a_pass_without_every_listing_restarts_the_count(self):
        tracker = AbsenceTracker()
        row = _row("d-1", "Unknown")
        partial = _listings()
        del partial["hyp-1"]

        tracker.absent([row], ONLINE, _listings(), NOT_HELD)
        tracker.absent([row], ONLINE, partial, NOT_HELD)

        assert _passes(tracker, [row], _listings(), 1) == []

    def test_a_row_on_a_hypervisor_that_is_not_online_is_never_due(self):
        row = _row("d-1", "Unknown", "hyp-gone")

        assert _passes(AbsenceTracker(), [row], _listings(), 5) == []

    def test_no_online_hypervisor_decides_nothing(self):
        """Right after an engine restart every hypervisor is still Offline."""
        assert (
            _passes(AbsenceTracker(), [_row("d-1", "Unknown")], {}, 5, online=[]) == []
        )

    def test_a_held_domain_is_never_due(self):
        row = _row("d-1", "Unknown", "hyp-1")

        assert (
            _passes(AbsenceTracker(), [row], _listings(), 5, is_held=lambda d: True)
            == []
        )

    def test_a_status_change_restarts_the_count(self):
        tracker = AbsenceTracker()
        tracker.absent([_row("d-1", "Started", "hyp-1")], ONLINE, _listings(), NOT_HELD)

        assert _passes(tracker, [_row("d-1", "Unknown", "hyp-1")], _listings(), 1) == []

    @pytest.mark.parametrize(
        "status", ["Starting", "Stopping", "Shutting-down", "Resetting", "Stopped"]
    )
    def test_rows_other_flows_own_are_left_alone(self, status):
        assert _passes(AbsenceTracker(), [_row("d-1", status)], _listings(), 5) == []


def _paused(vcpu_time, hyp="hyp-1", domain="d-1"):
    return {hyp: {domain: {"status": "Paused", "detail": "", "vcpu_time": vcpu_time}}}


class TestIdlePaused:
    def test_due_once_it_has_used_no_cpu_for_long_enough(self):
        tracker = IdlePausedTracker(after_s=600)
        statuses = {"d-1": "Paused"}

        assert tracker.due(_paused(0.2), statuses, NOT_HELD, now=1000) == []
        assert tracker.due(_paused(0.2), statuses, NOT_HELD, now=1599) == []
        assert tracker.due(_paused(0.2), statuses, NOT_HELD, now=1600) == [
            ("hyp-1", "d-1", "Paused", 0.2)
        ]

    def test_cpu_used_meanwhile_restarts_the_clock(self):
        tracker = IdlePausedTracker(after_s=600)
        statuses = {"d-1": "Paused"}
        tracker.due(_paused(0.2), statuses, NOT_HELD, now=1000)
        tracker.due(_paused(0.4), statuses, NOT_HELD, now=1300)

        assert tracker.due(_paused(0.4), statuses, NOT_HELD, now=1700) == []
        assert tracker.due(_paused(0.4), statuses, NOT_HELD, now=1900) != []

    def test_a_domain_that_ran_is_never_due(self):
        tracker = IdlePausedTracker(after_s=600)
        statuses = {"d-1": "Paused"}
        tracker.due(_paused(42.0), statuses, NOT_HELD, now=0)

        assert tracker.due(_paused(42.0), statuses, NOT_HELD, now=10_000) == []

    @pytest.mark.parametrize("status", STATUSES_NEVER_REAPED)
    def test_a_flow_still_running_is_never_due(self, status):
        tracker = IdlePausedTracker(after_s=600)
        tracker.due(_paused(0.1), {"d-1": status}, NOT_HELD, now=0)

        assert tracker.due(_paused(0.1), {"d-1": status}, NOT_HELD, now=10_000) == []

    def test_a_held_or_unknown_row_is_never_due(self):
        tracker = IdlePausedTracker(after_s=600)
        for now in (0, 10_000):
            assert (
                tracker.due(_paused(0.1), {"d-1": "Paused"}, lambda d: True, now) == []
            )
            assert tracker.due(_paused(0.1), {}, NOT_HELD, now) == []

    def test_the_guest_time_is_the_vcpus_not_the_domain_total(self):
        """A domain left paused at start keeps adding emulator time to its total
        (1.46 s after ten minutes, measured) while its vCPUs never ran."""
        dom = MagicMock()
        dom.info.return_value = [3, 0, 0, 2, 1_460_000_000]
        dom.vcpus.return_value = ([(0, 1, 0, 0), (1, 1, 0, 1)], [])

        assert vcpu_seconds(dom) == 0

    def test_candidates_are_the_paused_domains_with_almost_no_cpu(self):
        listings = {
            "hyp-1": {
                "idle": {"status": "Paused", "vcpu_time": 0.1},
                "ran": {"status": "Paused", "vcpu_time": 12.0},
                "up": {"status": "Started"},
            }
        }

        assert IdlePausedTracker.candidates(listings) == {"idle"}
