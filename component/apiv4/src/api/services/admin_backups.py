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

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


class AdminBackupsService:

    @staticmethod
    def _convert_timestamps(item: dict) -> dict:
        """Convert datetime/timestamp objects to ISO strings."""
        for field in ("timestamp", "created_at"):
            if field in item:
                if hasattr(item[field], "isoformat"):
                    item[field] = item[field].isoformat()
                elif isinstance(item[field], (int, float)):
                    ts = item[field]
                    if ts > 1e10:
                        ts = ts / 1000
                    item[field] = datetime.fromtimestamp(ts).isoformat()
        return item

    @staticmethod
    def list_backups() -> list:
        """Get list of backups, ordered by timestamp, limited to 30."""
        with RethinkSharedConnection._rdb_context():
            result = list(
                r.table("backups")
                .order_by(r.desc("timestamp"))
                .limit(30)
                .run(RethinkSharedConnection._rdb_connection)
            )
        for item in result:
            AdminBackupsService._convert_timestamps(item)
        return result

    @staticmethod
    def get_backup(backup_id: str, pluck: str = None) -> dict:
        """Get a specific backup by ID."""
        with RethinkSharedConnection._rdb_context():
            query = r.table("backups").get(backup_id)
            if pluck:
                query = query.pluck(*pluck)
            result = query.run(RethinkSharedConnection._rdb_connection)

        if not result:
            raise Error("not_found", "Backup not found")

        return AdminBackupsService._convert_timestamps(result)

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

        # Process details field
        if "details" in data and isinstance(data["details"], dict):
            details = data["details"]
            if "warnings" in details and not isinstance(details["warnings"], list):
                details["warnings"] = [str(details["warnings"])]
            if "time_breakdown" in details and not isinstance(
                details["time_breakdown"], dict
            ):
                details["time_breakdown"] = {}

        # Store the original client timestamp as backup_start_time
        if "timestamp" in data:
            data["backup_start_time"] = data["timestamp"]

        data["timestamp"] = r.now()
        if "created_at" not in data:
            data["created_at"] = r.now()

        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("backups")
                .insert(data)
                .run(RethinkSharedConnection._rdb_connection)
            )

        if result.get("inserted") == 1:
            backup_id = result["generated_keys"][0]
            AdminBackupsService._cleanup_old_backups()
            return {
                "id": backup_id,
                "status": "success",
                "message": "Backup record created successfully",
            }
        else:
            raise Error("internal_server", "Failed to create backup record")

    @staticmethod
    def _cleanup_old_backups():
        """Remove old backup records, keeping only the most recent 30."""
        with RethinkSharedConnection._rdb_context():
            total_count = (
                r.table("backups").count().run(RethinkSharedConnection._rdb_connection)
            )
            if total_count > 30:
                old_backup_ids = list(
                    r.table("backups")
                    .order_by(r.desc("timestamp"))
                    .skip(30)
                    .pluck("id")
                    .run(RethinkSharedConnection._rdb_connection)
                )
                if old_backup_ids:
                    ids_to_delete = [b["id"] for b in old_backup_ids]
                    r.table("backups").get_all(*ids_to_delete).delete().run(
                        RethinkSharedConnection._rdb_connection
                    )

    @staticmethod
    def get_backup_config() -> dict:
        """Get backup configuration from environment variables."""

        def parse_backup_schedule(schedule_env):
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
