# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the day-of-week schedule DECISION layer (pure).

These pin the recurring-schedule rules layered on top of the daily HH:MM window:
  * a window is open only on selected weekdays within the daily range,
  * an overnight window's post-midnight tail belongs to its START day,
  * the per-occurrence key (start date) is stable across a whole occurrence so
    the reconciler re-scans exactly once per occurrence,
  * next-occurrence lookahead for the admin table.
Weekdays are Mon=0 … Sun=6 (datetime.weekday()). The live wiring (now-in-tz,
ledger re-scan) is exercised in the reconciler.
"""

from datetime import datetime

from isardvdi_common.lib.storage import migration as mig

# Anchor dates with known weekdays (verified below): 2026-07 starts on a Wed.
WED = datetime(2026, 7, 1, 12, 0)  # weekday 2
FRI = datetime(2026, 7, 3, 23, 30)  # weekday 4
SAT = datetime(2026, 7, 4, 3, 0)  # weekday 5


def test_anchor_weekdays():
    assert WED.weekday() == 2
    assert FRI.weekday() == 4
    assert SAT.weekday() == 5


# --------------------------------------------------------------------------- #
# normalize_days
# --------------------------------------------------------------------------- #
def test_normalize_days_empty_is_all_days():
    assert mig.normalize_days(None) is None
    assert mig.normalize_days([]) is None


def test_normalize_days_valid_and_dedup():
    assert mig.normalize_days([5, 6, 5]) == {5, 6}
    assert mig.normalize_days(["0", 1]) == {0, 1}


def test_normalize_days_drops_out_of_range_and_junk():
    assert mig.normalize_days([7, -1, "x", 3]) == {3}
    # all-invalid collapses to None (every day) rather than never-open
    assert mig.normalize_days([7, 8]) is None


# --------------------------------------------------------------------------- #
# window_is_open_days — day filter combined with the time window
# --------------------------------------------------------------------------- #
def test_open_days_no_day_restriction_matches_time_only():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("23:30")
    now = mig.parse_hhmm("22:30")
    # empty days == every day: same as the plain time check
    assert mig.window_is_open_days(s, e, [], 2, now) is True
    assert mig.window_is_open_days(s, e, None, 2, mig.parse_hhmm("21:00")) is False


def test_open_days_same_day_gated_by_weekday():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    now = mig.parse_hhmm("12:00")
    assert mig.window_is_open_days(s, e, [2], 2, now) is True  # Wed selected
    assert mig.window_is_open_days(s, e, [0, 1], 2, now) is False  # Wed not selected


def test_open_days_time_closed_stays_closed_even_on_selected_day():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    assert mig.window_is_open_days(s, e, [2], 2, mig.parse_hhmm("18:00")) is False


def test_open_days_overnight_start_day():
    # Fri 22:00 -> Sat 06:00; the pre-midnight portion belongs to Friday(4)
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    now = mig.parse_hhmm("23:00")  # Friday night
    assert mig.window_is_open_days(s, e, [4], 4, now) is True  # Fri selected
    assert mig.window_is_open_days(s, e, [5], 4, now) is False  # only Sat selected


def test_open_days_overnight_tail_belongs_to_previous_day():
    # After midnight (Sat 03:00) the tail still belongs to Friday's occurrence.
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    now = mig.parse_hhmm("03:00")  # Saturday morning, weekday 5
    assert (
        mig.window_is_open_days(s, e, [4], 5, now) is True
    )  # Fri selected -> tail open
    assert (
        mig.window_is_open_days(s, e, [5], 5, now) is False
    )  # Sat-only -> tail closed


# --------------------------------------------------------------------------- #
# window_remaining_seconds_days
# --------------------------------------------------------------------------- #
def test_remaining_days_zero_when_day_closed():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    # Wed 12:00 but only Mon selected -> closed -> 0 remaining
    assert mig.window_remaining_seconds_days(s, e, [0], 2, mig.parse_hhmm("12:00")) == 0


def test_remaining_days_matches_time_remaining_when_open():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    now = mig.parse_hhmm("16:30")
    assert (
        mig.window_remaining_seconds_days(s, e, [2], 2, now)
        == mig.window_remaining_seconds(s, e, now)
        == 1800
    )


# --------------------------------------------------------------------------- #
# occurrence_key — stable per occurrence (re-scan exactly once)
# --------------------------------------------------------------------------- #
def test_occurrence_key_same_day_is_today():
    assert mig.occurrence_key(
        WED, mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    ) == ("2026-07-01")


def test_occurrence_key_overnight_prenight_is_start_date():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    assert mig.occurrence_key(FRI, s, e) == "2026-07-03"  # Fri 23:30 -> Fri


def test_occurrence_key_overnight_tail_is_previous_date():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    # Sat 03:00 tail still keys to Friday, so one occurrence = one key
    assert mig.occurrence_key(SAT, s, e) == "2026-07-03"


def test_occurrence_key_stable_across_one_overnight_occurrence():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("06:00")
    pre = mig.occurrence_key(datetime(2026, 7, 3, 23, 0), s, e)
    post = mig.occurrence_key(datetime(2026, 7, 4, 5, 0), s, e)
    assert pre == post == "2026-07-03"


# --------------------------------------------------------------------------- #
# next_occurrence_seconds — admin table lookahead
# --------------------------------------------------------------------------- #
def test_next_occurrence_open_now_is_zero():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    assert mig.next_occurrence_seconds(s, e, [2], 2, mig.parse_hhmm("12:00")) == 0


def test_next_occurrence_later_today():
    s, e = mig.parse_hhmm("22:00"), mig.parse_hhmm("23:00")
    now = mig.parse_hhmm("20:00")  # Wed, opens at 22:00 today
    assert mig.next_occurrence_seconds(s, e, [2], 2, now) == 2 * 3600


def test_next_occurrence_scans_forward_to_selected_day():
    s, e = mig.parse_hhmm("09:00"), mig.parse_hhmm("17:00")
    now = mig.parse_hhmm("12:00")  # Wed(2); only Sat(5) selected -> 3 days away
    # 3 days to Sat 00:00 then +9h to 09:00, minus the 12h already elapsed today
    expected = (3 * 1440 + mig.parse_hhmm("09:00") - now) * 60
    assert mig.next_occurrence_seconds(s, e, [5], 2, now) == expected


def test_next_occurrence_none_when_no_schedule():
    # no time bounds and no day restriction == always open, no next-run
    assert mig.next_occurrence_seconds(None, None, [], 2, 720) is None
