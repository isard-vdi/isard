#
#   Copyright © 2025 IsardVDI
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
import re
from datetime import datetime
from typing import Optional

from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.backups.backups import BackupsProcessed
from isardvdi_common.models.config import Config

# Integrity check toggle. Stored at config[1].backups.integrity_enabled.
# Off by default: borg check is an expensive full-repo verification, and we
# don't want existing deployments to silently inherit a multi-hour nightly
# job. Admins opt in from the webapp; the backupninja container fetches the
# value at boot and schedules the integrity scripts for Saturday only.
INTEGRITY_ENABLED_DEFAULT = False


def _retention() -> int:
    """How many backup records to keep. Configurable via env."""
    try:
        value = int(os.environ.get("BACKUP_RETENTION", "30"))
    except ValueError:
        value = 30
    return max(1, value)


def _normalize_timestamp(
    value: Optional[datetime | int | float | str],
) -> Optional[str]:
    """Return ISO string for a RethinkDB datetime, Unix int, or ISO string."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e10 else value
        return datetime.fromtimestamp(ts).isoformat()
    return value


def _normalize_times(item: dict) -> dict:
    for key in ("timestamp", "received_at", "created_at", "backup_start_time"):
        if key in item:
            item[key] = _normalize_timestamp(item[key])
    return item


def _normalize_check(check: dict | str) -> dict:
    if isinstance(check, dict) and "name" in check and "status" in check:
        return check
    if isinstance(check, str):
        return {"name": check, "status": "success"}
    return {"name": str(check), "status": "success"}


class AdminBackupsService:

    @staticmethod
    def list_backups(limit: Optional[int] = None) -> list[dict]:
        """List backup records ordered most-recent-first."""
        if limit is None:
            limit = _retention()

        result = BackupsProcessed.list_recent(limit)
        for item in result:
            _normalize_times(item)
        return result

    @staticmethod
    def get_backup(backup_id: str, pluck: Optional[str] = None) -> dict:
        """Get a specific backup by ID."""
        result = BackupsProcessed.get(backup_id, pluck=list(pluck) if pluck else None)

        if not result:
            raise Error("not_found", "Backup not found")

        return _normalize_times(result)

    @staticmethod
    def insert_backup(data: dict) -> dict:
        """Insert a new backup record (used by backupninja service)."""
        required_fields = ["timestamp", "status", "type", "scope"]
        for field in required_fields:
            if field not in data:
                raise Error("bad_request", f"Missing required field: {field}")

        if data["type"] not in ["automated", "manual"]:
            raise Error("bad_request", "Backup type must be 'automated' or 'manual'")

        valid_scopes = ["full", "db", "redis", "stats", "config", "disks"]
        if data["scope"] not in valid_scopes:
            raise Error(
                "bad_request",
                f"Backup scope must be one of: {', '.join(valid_scopes)}",
            )

        if "details" in data and isinstance(data["details"], dict):
            details = data["details"]
            if "checks" in details and isinstance(details["checks"], list):
                details["checks"] = [_normalize_check(c) for c in details["checks"]]
            if "warnings" in details and not isinstance(details["warnings"], list):
                details["warnings"] = [str(details["warnings"])]
            if "time_breakdown" in details and not isinstance(
                details["time_breakdown"], dict
            ):
                details["time_breakdown"] = {}

        # ``BackupsProcessed.insert`` coerces ``timestamp`` to a ReQL
        # datetime and stamps ``received_at`` / ``created_at`` server-side
        # so indexes and ordering work regardless of the client's clock
        # format.
        result = BackupsProcessed.insert(data)

        if result.get("inserted") != 1:
            raise Error("internal_server", "Failed to create backup record")

        backup_id = result["generated_keys"][0]
        AdminBackupsService._cleanup_old_backups()

        # Email admins when the backup did not finish cleanly. Imported lazily
        # so this module does not depend on the notifier at import time.
        if data.get("status") in ("CRITICAL", "ERROR"):
            try:
                from isardvdi_common.connections.api_notifier import (
                    notify_backup_failure,
                )

                notify_backup_failure(data)
            except Exception:
                # Never let notification problems fail the insert.
                pass

        return {
            "id": backup_id,
            "status": "success",
            "message": "Backup record created successfully",
        }

    @staticmethod
    def _cleanup_old_backups() -> int:
        """Keep only the N most recent backup records (N = BACKUP_RETENTION)."""
        keep = _retention()

        if BackupsProcessed.count() <= keep:
            return 0

        old_ids = BackupsProcessed.list_old_ids(keep)
        return BackupsProcessed.delete_many(old_ids)

    @staticmethod
    def get_integrity_enabled() -> bool:
        """Return the saved weekly-borg-integrity toggle (default off)."""
        value = Config.get_backups_integrity_enabled()
        if value is None:
            return INTEGRITY_ENABLED_DEFAULT
        return value

    @staticmethod
    def set_integrity_enabled(value: bool) -> dict:
        """Persist the weekly-borg-integrity toggle. Schemaless config write."""
        if not isinstance(value, bool):
            raise Error("bad_request", "integrity_enabled must be a boolean")
        Config.set_backups_integrity_enabled(value)
        return {"integrity_enabled": value}

    @staticmethod
    def get_backup_config() -> dict:
        """Get backup configuration from environment variables."""

        def parse_backup_schedule(schedule_env: str) -> Optional[int]:
            if not schedule_env:
                return None
            match = re.search(r"at\s+(\d{1,2})(?::\d{2})?", schedule_env)
            if match:
                return int(match.group(1))
            return None

        config = {
            "schedule": {
                "db": parse_backup_schedule(os.getenv("BACKUP_DB_WHEN", "")),
                "redis": parse_backup_schedule(os.getenv("BACKUP_REDIS_WHEN", "")),
                "stats": parse_backup_schedule(os.getenv("BACKUP_STATS_WHEN", "")),
                "config": parse_backup_schedule(os.getenv("BACKUP_CONFIG_WHEN", "")),
                "disks": parse_backup_schedule(os.getenv("BACKUP_DISKS_WHEN", "")),
            },
            "enabled": {
                "db": os.getenv("BACKUP_DB_ENABLED", "false").lower() == "true",
                "redis": os.getenv("BACKUP_REDIS_ENABLED", "false").lower() == "true",
                "stats": os.getenv("BACKUP_STATS_ENABLED", "false").lower() == "true",
                "config": os.getenv("BACKUP_CONFIG_ENABLED", "false").lower() == "true",
                "disks": os.getenv("BACKUP_DISKS_ENABLED", "false").lower() == "true",
            },
        }

        schedule_hours = [h for h in config["schedule"].values() if h is not None]
        if schedule_hours:
            config["main_schedule_hour"] = max(
                set(schedule_hours), key=schedule_hours.count
            )
        else:
            config["main_schedule_hour"] = 19

        return config
