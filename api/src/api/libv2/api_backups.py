#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import os
from datetime import datetime

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


UNKNOWN_HOST = "unknown-host"

# Integrity check toggle. Stored at config[1].backups.integrity_enabled.
# Off by default: borg check is an expensive full-repo verification, and we
# don't want existing deployments to silently inherit a multi-hour nightly
# job. Admins opt in from the webapp; the backupninja container fetches the
# value at boot and schedules the integrity scripts for Saturday only.
INTEGRITY_ENABLED_DEFAULT = False


def get_integrity_enabled():
    with app.app_context():
        cfg = r.table("config").get(1).run(db.conn) or {}
    value = (cfg.get("backups") or {}).get("integrity_enabled")
    if value is None:
        return INTEGRITY_ENABLED_DEFAULT
    return bool(value)


def set_integrity_enabled(value):
    if not isinstance(value, bool):
        raise Error("bad_request", "integrity_enabled must be a boolean")
    with app.app_context():
        r.table("config").get(1).update({"backups": {"integrity_enabled": value}}).run(
            db.conn
        )
    return {"integrity_enabled": value}


def _retention_per_host():
    """How many records to keep per host. Configurable via env."""
    try:
        value = int(os.environ.get("BACKUP_RETENTION_PER_HOST", "30"))
    except ValueError:
        value = 30
    return max(1, value)


def _normalize_timestamp(value):
    """Return ISO string for a RethinkDB datetime, Unix int, or ISO string."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e10 else value
        return datetime.fromtimestamp(ts).isoformat()
    return value


def _normalize_times(item):
    for key in ("timestamp", "received_at", "created_at", "backup_start_time"):
        if key in item:
            item[key] = _normalize_timestamp(item[key])
    return item


def admin_backup_list(host=None, limit=None):
    """
    Get list of backups for admin users. Returns most recent first, grouped
    across hosts. Pass host= to restrict to one host.
    """
    with app.app_context():
        if host:
            query = (
                r.table("backups")
                .filter(lambda row: row["host"].default(UNKNOWN_HOST) == host)
                .order_by(r.desc("timestamp"))
            )
        else:
            query = r.table("backups").order_by(r.desc("timestamp"))

        if limit is None:
            limit = _retention_per_host()
            if not host:
                limit *= 10  # show more across hosts
        query = query.limit(limit)

        result = list(query.run(db.conn))
        for item in result:
            _normalize_times(item)
        return result


def admin_backup_hosts():
    """Distinct list of hosts that have ever reported a backup.

    Uses .default() to tolerate pre-feature rows that lack the host field;
    they surface as UNKNOWN_HOST rather than crashing the query.
    """
    with app.app_context():
        return sorted(
            r.table("backups")
            .map(lambda row: row["host"].default(UNKNOWN_HOST))
            .distinct()
            .run(db.conn)
        )


def admin_backup_get(backup_id, pluck=None):
    """
    Get a specific backup by ID
    """
    with app.app_context():
        query = r.table("backups").get(backup_id)

        if pluck:
            query = query.pluck(*pluck)

        result = query.run(db.conn)
        if not result:
            raise Error("not_found", "Backup not found")

        _normalize_times(result)
        return result


def cleanup_old_backups(host):
    """
    Remove old backup records for a single host, keeping only the N most
    recent entries (N = BACKUP_RETENTION_PER_HOST, default 30).
    """
    if not host:
        host = UNKNOWN_HOST
    keep = _retention_per_host()

    with app.app_context():
        host_filter = lambda row: row["host"].default(UNKNOWN_HOST) == host
        total_count = r.table("backups").filter(host_filter).count().run(db.conn)
        if total_count <= keep:
            return 0

        old_ids = [
            row["id"]
            for row in r.table("backups")
            .filter(host_filter)
            .order_by(r.desc("timestamp"))
            .skip(keep)
            .pluck("id")
            .run(db.conn)
        ]
        if not old_ids:
            return 0

        result = r.table("backups").get_all(*old_ids).delete().run(db.conn)
        return result.get("deleted", 0)


def admin_backup_insert(data):
    """
    Insert a new backup record (used by backupninja service).
    """
    required_fields = ["timestamp", "status", "type", "scope"]
    for field in required_fields:
        if field not in data:
            raise Error("bad_request", f"Missing required field: {field}")

    if data["type"] not in ["automated", "manual"]:
        raise Error("bad_request", "Backup type must be 'automated' or 'manual'")

    valid_scopes = ["full", "db", "redis", "stats", "config", "disks"]
    if data["scope"] not in valid_scopes:
        raise Error(
            "bad_request", f"Backup scope must be one of: {', '.join(valid_scopes)}"
        )

    host = data.get("host") or UNKNOWN_HOST
    data["host"] = host

    if "details" in data and isinstance(data["details"], dict):
        details = data["details"]
        if "checks" in details and isinstance(details["checks"], list):
            details["checks"] = [_normalize_check(check) for check in details["checks"]]
        if "warnings" in details and not isinstance(details["warnings"], list):
            details["warnings"] = [str(details["warnings"])]
        if "time_breakdown" in details and not isinstance(
            details["time_breakdown"], dict
        ):
            details["time_breakdown"] = {}

    # Preserve the client-supplied timestamp as the authoritative backup time.
    # Unix ints become RethinkDB datetimes so indexes and ordering work.
    data["timestamp"] = _client_timestamp_to_rdb(data["timestamp"])
    data["received_at"] = r.now()
    data.setdefault("created_at", data["received_at"])

    result = r.table("backups").insert(data).run(db.conn)
    if result.get("inserted") != 1:
        raise Error("internal_error", "Failed to create backup record")

    backup_id = result["generated_keys"][0]
    cleanup_old_backups(host)

    return {
        "id": backup_id,
        "status": "success",
        "message": "Backup record created successfully",
    }


def _client_timestamp_to_rdb(value):
    """Accept Unix int/float/ISO string and return a ReQL time."""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e10 else value
        return r.epoch_time(seconds)
    if isinstance(value, str):
        try:
            return r.iso8601(value)
        except Exception:
            return r.now()
    if hasattr(value, "isoformat"):
        return r.iso8601(value.isoformat())
    return r.now()


def _normalize_check(check):
    if isinstance(check, dict) and "name" in check and "status" in check:
        return check
    if isinstance(check, str):
        return {"name": check, "status": "success"}
    return {"name": str(check), "status": "success"}


def admin_backup_update(backup_id, data):
    """
    Backup records are immutable once written.
    """
    raise Error("forbidden", "Backup records cannot be modified")


def admin_backup_delete(backup_id):
    """
    Backup records are immutable once written.
    """
    raise Error("forbidden", "Backup records cannot be deleted")
