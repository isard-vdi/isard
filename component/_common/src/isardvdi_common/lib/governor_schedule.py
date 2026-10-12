#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Time-of-day profiles for the storage governor's ``max_heavy`` cap."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MAX_PROFILES = 16
MAX_HEAVY_MIN = 1
MAX_HEAVY_MAX = 64
DEFAULT_TZ = "UTC"


def parse_hhmm(value):
    """``"HH:MM"`` -> minutes since midnight, or ``None`` if unset/invalid."""
    if not isinstance(value, str):
        return None
    try:
        h, m = value.split(":")
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h * 60 + m


def _clean_days(days):
    if days is None:
        return []
    if not isinstance(days, (list, tuple)):
        return None
    out = set()
    for d in days:
        if isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6:
            return None
        out.add(d)
    return sorted(out)


def clean_profile(raw):
    """Normalised entry, or the reason it is rejected as a string."""
    if not isinstance(raw, dict):
        return "each schedule entry must be an object"
    start, end = parse_hhmm(raw.get("start")), parse_hhmm(raw.get("end"))
    if start is None or end is None:
        return "start and end must be HH:MM"
    if start == end:
        return "start and end must differ"
    days = _clean_days(raw.get("days"))
    if days is None:
        return "days must be a list of weekdays 0 (Monday) to 6 (Sunday)"
    value = raw.get("max_heavy")
    if isinstance(value, bool) or not isinstance(value, int):
        return "max_heavy must be an integer"
    if not MAX_HEAVY_MIN <= value <= MAX_HEAVY_MAX:
        return f"max_heavy must be between {MAX_HEAVY_MIN} and {MAX_HEAVY_MAX}"
    return {
        "start": raw["start"],
        "end": raw["end"],
        "days": days,
        "max_heavy": value,
    }


def zone(tz):
    """``ZoneInfo`` for ``tz`` (UTC when unset), or ``None`` if unknown."""
    try:
        return ZoneInfo(tz or DEFAULT_TZ)
    except Exception:
        return None


def _is_open(start, end, days, weekday, now_min):
    if start < end:
        if not start <= now_min < end:
            return False
        started_on = weekday
    else:  # the post-midnight tail belongs to the day the range started
        if not (now_min >= start or now_min < end):
            return False
        started_on = (weekday - 1) % 7 if now_min < end else weekday
    return not days or started_on in days


def active_profile(block, now=None):
    """Index of the first schedule entry open at ``now``, or ``None``."""
    block = block or {}
    schedule = block.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        return None
    tz = zone(block.get("schedule_tz"))
    if tz is None:  # wrong hours would be worse than the flat cap
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    now_min = now.hour * 60 + now.minute
    for index, raw in enumerate(schedule[:MAX_PROFILES]):
        profile = clean_profile(raw)
        if isinstance(profile, str):
            continue
        if _is_open(
            parse_hhmm(profile["start"]),
            parse_hhmm(profile["end"]),
            profile["days"],
            now.weekday(),
            now_min,
        ):
            return index
    return None


def effective_max_heavy(block, base, now=None):
    """``(cap, index of the entry that set it or None for the flat base)``."""
    index = active_profile(block, now)
    if index is None:
        return base, None
    return block["schedule"][index]["max_heavy"], index
