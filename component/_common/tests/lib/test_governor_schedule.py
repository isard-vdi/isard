# SPDX-License-Identifier: AGPL-3.0-or-later

"""Time-of-day profiles for the governor's heavy cap."""

from datetime import datetime, timezone

import pytest
from isardvdi_common.lib import governor_schedule as gs

NIGHT = {"start": "22:55", "end": "07:20", "max_heavy": 4}


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _block(*profiles, tz=None, max_heavy=2):
    block = {"max_heavy": max_heavy, "schedule": list(profiles)}
    if tz is not None:
        block["schedule_tz"] = tz
    return block


@pytest.mark.parametrize(
    "now, expected",
    [
        (_utc(2026, 10, 12, 22, 54), (2, None)),
        (_utc(2026, 10, 12, 22, 55), (4, 0)),
        (_utc(2026, 10, 13, 3, 0), (4, 0)),
        (_utc(2026, 10, 13, 7, 19), (4, 0)),
        (_utc(2026, 10, 13, 7, 20), (2, None)),
        (_utc(2026, 10, 13, 12, 0), (2, None)),
    ],
)
def test_overnight_profile_holds_from_start_until_end(now, expected):
    assert gs.effective_max_heavy(_block(NIGHT), 2, now) == expected


def test_no_schedule_keeps_the_flat_cap():
    assert gs.effective_max_heavy({"max_heavy": 3}, 3, _utc(2026, 10, 13, 3)) == (
        3,
        None,
    )
    assert gs.effective_max_heavy({}, 2, _utc(2026, 10, 13, 3)) == (2, None)
    assert gs.effective_max_heavy(None, 2, _utc(2026, 10, 13, 3)) == (2, None)


def test_hours_are_read_in_the_schedule_zone():
    # 21:00 UTC is 23:00 in Madrid (CEST, UTC+2): inside the night profile there,
    # outside it if the same hours were read as UTC.
    now = _utc(2026, 10, 12, 21, 0)
    assert gs.effective_max_heavy(_block(NIGHT, tz="Europe/Madrid"), 2, now) == (4, 0)
    assert gs.effective_max_heavy(_block(NIGHT), 2, now) == (2, None)


def test_daylight_saving_change_follows_the_wall_clock():
    # 25/10/2026 Europe/Madrid falls back to CET (UTC+1): 22:55 local is 21:55 UTC.
    block = _block(NIGHT, tz="Europe/Madrid")
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 26, 21, 54)) == (2, None)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 26, 21, 55)) == (4, 0)


def test_days_filter_on_the_weekday_the_range_starts():
    weekdays = dict(NIGHT, days=[0, 1, 2, 3, 4])  # Monday..Friday nights
    block = _block(weekdays)
    # Friday 23:00 -> open; its Saturday 03:00 tail belongs to Friday -> open.
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 16, 23)) == (4, 0)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 17, 3)) == (4, 0)
    # Saturday 23:00 and its Sunday tail -> closed; Sunday 23:00 -> closed.
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 17, 23)) == (2, None)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 18, 3)) == (2, None)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 18, 23)) == (2, None)
    # Monday 03:00 is Sunday night's tail -> closed.
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 19, 3)) == (2, None)


def test_first_open_profile_wins():
    weekend = {"start": "00:00", "end": "23:59", "days": [5, 6], "max_heavy": 6}
    block = _block(weekend, NIGHT)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 17, 23, 30)) == (6, 0)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 16, 23, 30)) == (4, 1)


def test_unknown_zone_disables_the_schedule():
    block = _block(NIGHT, tz="Mars/Olympus")
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 13, 3)) == (2, None)


def test_an_invalid_entry_is_skipped_not_fatal():
    broken = {"start": "25:00", "end": "07:00", "max_heavy": 9}
    block = _block(broken, NIGHT)
    assert gs.effective_max_heavy(block, 2, _utc(2026, 10, 13, 3)) == (4, 1)


@pytest.mark.parametrize(
    "raw, reason",
    [
        ("22:00-06:00", "object"),
        ({"start": "22:00", "max_heavy": 4}, "HH:MM"),
        ({"start": "22:00", "end": "24:00", "max_heavy": 4}, "HH:MM"),
        ({"start": "22:00", "end": "22:00", "max_heavy": 4}, "differ"),
        ({"start": "22:00", "end": "06:00", "days": [7], "max_heavy": 4}, "weekdays"),
        ({"start": "22:00", "end": "06:00", "days": "mon", "max_heavy": 4}, "weekdays"),
        ({"start": "22:00", "end": "06:00", "max_heavy": "4"}, "integer"),
        ({"start": "22:00", "end": "06:00", "max_heavy": True}, "integer"),
        ({"start": "22:00", "end": "06:00", "max_heavy": 0}, "between"),
        ({"start": "22:00", "end": "06:00", "max_heavy": 65}, "between"),
    ],
)
def test_clean_profile_rejects(raw, reason):
    out = gs.clean_profile(raw)
    assert isinstance(out, str) and reason in out


def test_clean_profile_normalises_days():
    out = gs.clean_profile(
        {"start": "22:00", "end": "06:00", "days": [4, 0, 4], "max_heavy": 4}
    )
    assert out == {"start": "22:00", "end": "06:00", "days": [0, 4], "max_heavy": 4}
