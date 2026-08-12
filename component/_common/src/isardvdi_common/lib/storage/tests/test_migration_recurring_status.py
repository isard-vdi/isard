# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the end-of-tick next-status DECISION (pure) — the SETTLED
shape of the recurring vs one-shot lifecycle.

  * one-shot preserves today's behaviour (complete -> completed/failed; while
    draining the window branch flips running<->window_closed, returned as None
    here so the caller keeps its existing logic),
  * recurring NEVER self-terminates: complete -> ``scheduled`` (idle), otherwise
    ``running`` while in-window or with an in-flight tree, else ``scheduled``,
  * a cancel in progress (``finishing``) -> ``canceled`` once complete.

HELD (marked in the helper): the recurring FAILURE policy — a failed tree keeps a
recurring job alive here; quarantine-after-N vs pause-for-attention is set later.
The re-scan CADENCE is a separate HELD hook in ``_maybe_rescan_occurrence``.
"""

from isardvdi_common.lib.storage import migration as mig


def T(**kw):
    base = dict(
        is_complete=False,
        any_in_flight=False,
        win_open=True,
        finishing=False,
        any_failed=False,
        recurring=False,
    )
    base.update(kw)
    return mig.recurring_status_target(**base)


# --------------------------------------------------------------------------- #
# one-shot
# --------------------------------------------------------------------------- #
def test_oneshot_complete_completed():
    assert T(recurring=False, is_complete=True) == "completed"


def test_oneshot_complete_failed_when_any_failed():
    assert T(recurring=False, is_complete=True, any_failed=True) == "failed"


def test_oneshot_incomplete_defers_to_caller():
    # running<->window_closed is handled by the existing window branch -> None
    assert T(recurring=False, is_complete=False) is None


# --------------------------------------------------------------------------- #
# recurring — never self-terminates
# --------------------------------------------------------------------------- #
def test_recurring_complete_goes_idle_not_completed():
    assert T(recurring=True, is_complete=True) == "scheduled"


def test_recurring_complete_stays_idle_even_with_failure():
    # HELD failure policy: a failed tree does NOT terminalize a recurring job
    assert T(recurring=True, is_complete=True, any_failed=True) == "scheduled"


def test_recurring_draining_in_window_runs():
    assert T(recurring=True, is_complete=False, win_open=True) == "running"


def test_recurring_in_flight_out_of_window_keeps_running():
    # in-flight trees always finish, even once the window closed
    assert (
        T(recurring=True, is_complete=False, win_open=False, any_in_flight=True)
        == "running"
    )


def test_recurring_idle_between_occurrences():
    # window closed, nothing in flight, not complete -> idle/scheduled
    assert (
        T(recurring=True, is_complete=False, win_open=False, any_in_flight=False)
        == "scheduled"
    )


# --------------------------------------------------------------------------- #
# cancel in progress
# --------------------------------------------------------------------------- #
def test_finishing_complete_cancels():
    assert T(finishing=True, is_complete=True) == "canceled"
    assert T(finishing=True, is_complete=True, recurring=True) == "canceled"


def test_finishing_incomplete_defers_to_caller():
    assert T(finishing=True, is_complete=False) is None
