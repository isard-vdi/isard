#
#   Copyright © 2026 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Simple REST list/summary endpoints for logs_desktops and logs_users.

These complement the existing DataTables POST endpoints with GET endpoints
that return plain JSON, making external integration straightforward.
"""

from datetime import datetime, timedelta, timezone

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)

_DESKTOP_LOG_FIELDS = [
    "id",
    "desktop_id",
    "desktop_name",
    "owner_user_id",
    "owner_user_name",
    "owner_category_id",
    "owner_category_name",
    "owner_group_id",
    "owner_group_name",
    "starting_time",
    "started_time",
    "stopping_time",
    "stopped_time",
    "starting_by",
    "stopping_by",
    "request_ip",
    "request_agent_browser",
    "request_agent_platform",
]

_USER_LOG_FIELDS = [
    "id",
    "owner_user_id",
    "owner_user_name",
    "owner_category_id",
    "owner_category_name",
    "owner_group_id",
    "owner_group_name",
    "started_time",
    "stopped_time",
    "expiry_time",
    "request_ip",
    "request_agent_browser",
    "request_agent_platform",
]

_list_desktops_cache = TTLCache(maxsize=50, ttl=30)
_list_users_cache = TTLCache(maxsize=50, ttl=30)
_summary_cache = TTLCache(maxsize=20, ttl=60)
_summary_past_cache = TTLCache(maxsize=50, ttl=300)


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        raise Error("bad_request", f"Invalid date format: {date_str}")


def _parse_limit(limit_str, default=500, maximum=10000):
    if not limit_str:
        return default
    try:
        val = int(limit_str)
        return max(1, min(val, maximum))
    except (ValueError, TypeError):
        return default


def _parse_offset(offset_str):
    if not offset_str:
        return 0
    try:
        return max(0, int(offset_str))
    except (ValueError, TypeError):
        return 0


def _cache_key_desktop_list(
    category_id, start_date, end_date, limit, offset, desktop_id, user_id, status
):
    return hashkey(
        category_id, start_date, end_date, limit, offset, desktop_id, user_id, status
    )


def _cache_key_user_list(
    category_id, start_date, end_date, limit, offset, user_id, group_id
):
    return hashkey(category_id, start_date, end_date, limit, offset, user_id, group_id)


def list_desktop_logs(
    payload,
    start_date=None,
    end_date=None,
    limit=500,
    offset=0,
    desktop_id=None,
    user_id=None,
    status=None,
):
    category_id = (
        payload["category_id"] if payload.get("role_id") == "manager" else None
    )

    return _list_desktop_logs_cached(
        category_id, start_date, end_date, limit, offset, desktop_id, user_id, status
    )


@cached(
    cache=_list_desktops_cache,
    key=_cache_key_desktop_list,
)
def _list_desktop_logs_cached(
    category_id, start_date, end_date, limit, offset, desktop_id, user_id, status
):
    with app.app_context():
        q = r.table("logs_desktops")

        if desktop_id:
            q = q.get_all(desktop_id, index="desktop_id")
            if start_date and end_date:
                q = q.filter(
                    lambda row: row["starting_time"].during(
                        r.expr(start_date), r.expr(end_date)
                    )
                )
            elif start_date:
                q = q.filter(lambda row: row["starting_time"] >= r.expr(start_date))
            elif end_date:
                q = q.filter(lambda row: row["starting_time"] < r.expr(end_date))
        elif start_date and end_date:
            q = q.between(
                r.expr(start_date),
                r.expr(end_date),
                index="starting_time",
            )
        elif start_date:
            q = q.between(
                r.expr(start_date),
                r.maxval,
                index="starting_time",
            )
        elif end_date:
            q = q.between(
                r.minval,
                r.expr(end_date),
                index="starting_time",
            )

        if category_id:
            q = q.filter({"owner_category_id": category_id})
        if user_id:
            q = q.filter({"owner_user_id": user_id})
        if status:
            q = q.filter({"stopped_status": status})

        total = q.count().run(db.conn)

        items = list(
            q.order_by(r.desc("starting_time"))
            .skip(offset)
            .limit(limit)
            .pluck(_DESKTOP_LOG_FIELDS + ["events"])
            .merge(
                lambda row: {
                    "events_count": row["events"].default([]).count(),
                }
            )
            .without("events")
            .run(db.conn)
        )

        return {"total": total, "items": items}


def list_user_logs(
    payload,
    start_date=None,
    end_date=None,
    limit=500,
    offset=0,
    user_id=None,
    group_id=None,
):
    category_id = (
        payload["category_id"] if payload.get("role_id") == "manager" else None
    )

    return _list_user_logs_cached(
        category_id, start_date, end_date, limit, offset, user_id, group_id
    )


@cached(
    cache=_list_users_cache,
    key=_cache_key_user_list,
)
def _list_user_logs_cached(
    category_id, start_date, end_date, limit, offset, user_id, group_id
):
    with app.app_context():
        q = r.table("logs_users")

        if user_id:
            q = q.get_all(user_id, index="owner_user_id")
            if start_date and end_date:
                q = q.filter(
                    lambda row: row["started_time"].during(
                        r.expr(start_date), r.expr(end_date)
                    )
                )
            elif start_date:
                q = q.filter(lambda row: row["started_time"] >= r.expr(start_date))
            elif end_date:
                q = q.filter(lambda row: row["started_time"] < r.expr(end_date))
        elif start_date and end_date:
            q = q.between(
                r.expr(start_date),
                r.expr(end_date),
                index="started_time",
            )
        elif start_date:
            q = q.between(
                r.expr(start_date),
                r.maxval,
                index="started_time",
            )
        elif end_date:
            q = q.between(
                r.minval,
                r.expr(end_date),
                index="started_time",
            )

        if category_id:
            q = q.filter({"owner_category_id": category_id})
        if group_id:
            q = q.filter({"owner_group_id": group_id})

        total = q.count().run(db.conn)

        items = list(
            q.order_by(r.desc("started_time"))
            .skip(offset)
            .limit(limit)
            .pluck(_USER_LOG_FIELDS)
            .run(db.conn)
        )

        return {"total": total, "items": items}


def usage_summary(payload, date_str=None):
    if not date_str:
        day_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        day_start = _parse_date(date_str)
        if day_start is None:
            raise Error("bad_request", "Invalid date")
        day_start = day_start.replace(hour=0, minute=0, second=0, microsecond=0)

    day_end = day_start + timedelta(days=1)
    is_past = day_end < datetime.now(timezone.utc)

    category_id = (
        payload["category_id"] if payload.get("role_id") == "manager" else None
    )

    cache = _summary_past_cache if is_past else _summary_cache
    cache_key = hashkey(category_id, day_start.isoformat())

    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    result = _compute_usage_summary(category_id, day_start, day_end)
    cache[cache_key] = result
    return result


def _compute_usage_summary(category_id, day_start, day_end):
    with app.app_context():
        # Desktop sessions
        dq = r.table("logs_desktops").between(
            r.expr(day_start),
            r.expr(day_end),
            index="starting_time",
        )
        if category_id:
            dq = dq.filter({"owner_category_id": category_id})

        desktop_by_hour = list(
            dq.group(r.row["starting_time"].hours())
            .ungroup()
            .map(
                lambda group: {
                    "hour": group["group"],
                    "started": group["reduction"].count(),
                    "unique_desktops": group["reduction"]
                    .map(lambda row: row["desktop_id"])
                    .distinct()
                    .count(),
                    "unique_users": group["reduction"]
                    .map(lambda row: row["owner_user_id"])
                    .distinct()
                    .count(),
                }
            )
            .run(db.conn)
        )

        desktop_totals = (
            dq.pluck("desktop_id", "owner_user_id")
            .fold(
                {"count": 0, "desktops": [], "users": []},
                lambda acc, row: {
                    "count": acc["count"].add(1),
                    "desktops": acc["desktops"].append(row["desktop_id"]),
                    "users": acc["users"].append(row["owner_user_id"]),
                },
            )
            .merge(
                lambda row: {
                    "unique_desktops": row["desktops"].distinct().count(),
                    "unique_users": row["users"].distinct().count(),
                }
            )
            .without("desktops", "users")
            .run(db.conn)
        )

        # Fill all 24 hours
        hour_map = {h["hour"]: h for h in desktop_by_hour}
        by_hour = []
        for h in range(24):
            if h in hour_map:
                by_hour.append(hour_map[h])
            else:
                by_hour.append(
                    {
                        "hour": h,
                        "started": 0,
                        "unique_desktops": 0,
                        "unique_users": 0,
                    }
                )

        # User sessions
        uq = r.table("logs_users").between(
            r.expr(day_start),
            r.expr(day_end),
            index="started_time",
        )
        if category_id:
            uq = uq.filter({"owner_category_id": category_id})

        user_totals = (
            uq.pluck("owner_user_id", "request_ip")
            .fold(
                {"count": 0, "users": [], "ips": []},
                lambda acc, row: {
                    "count": acc["count"].add(1),
                    "users": acc["users"].append(row["owner_user_id"]),
                    "ips": acc["ips"].append(row["request_ip"].default("unknown")),
                },
            )
            .merge(
                lambda row: {
                    "unique_users": row["users"].distinct().count(),
                    "unique_ips": row["ips"].distinct().count(),
                }
            )
            .without("users", "ips")
            .run(db.conn)
        )

        return {
            "date": day_start.strftime("%Y-%m-%d"),
            "desktops": {
                "total_sessions": desktop_totals.get("count", 0),
                "unique_desktops": desktop_totals.get("unique_desktops", 0),
                "unique_users": desktop_totals.get("unique_users", 0),
                "by_hour": by_hour,
            },
            "users": {
                "total_logins": user_totals.get("count", 0),
                "unique_users": user_totals.get("unique_users", 0),
                "unique_ips": user_totals.get("unique_ips", 0),
            },
        }
