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

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import json
from datetime import datetime

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def admin_backup_list():
    """
    Get list of backups for admin users (simplified for 30 records)
    """
    with app.app_context():
        # Simple query - no indexes needed for 30 records
        query = r.table("backups").order_by(r.desc("timestamp")).limit(30)
        result = list(query.run(db.conn))

        # Convert datetime/timestamp objects to ISO strings in Python
        for item in result:
            if "timestamp" in item:
                if hasattr(item["timestamp"], "isoformat"):
                    # It's a datetime object
                    item["timestamp"] = item["timestamp"].isoformat()
                elif isinstance(item["timestamp"], (int, float)):
                    # It's a Unix timestamp
                    from datetime import datetime

                    ts = item["timestamp"]
                    # If timestamp is > 1e10, it's likely in milliseconds
                    if ts > 1e10:
                        ts = ts / 1000
                    item["timestamp"] = datetime.fromtimestamp(ts).isoformat()
            if "created_at" in item:
                if hasattr(item["created_at"], "isoformat"):
                    item["created_at"] = item["created_at"].isoformat()
                elif isinstance(item["created_at"], (int, float)):
                    from datetime import datetime

                    ts = item["created_at"]
                    # If timestamp is > 1e10, it's likely in milliseconds
                    if ts > 1e10:
                        ts = ts / 1000
                    item["created_at"] = datetime.fromtimestamp(ts).isoformat()

        return result


def admin_backup_get(backup_id, pluck=None):
    """
    Get a specific backup by ID
    """
    with app.app_context():
        query = r.table("backups").get(backup_id)

        if pluck:
            query = query.pluck(*pluck)

        result = query.run(db.conn)
        if result:
            # Convert datetime/timestamp objects to ISO strings in Python
            if "timestamp" in result:
                if hasattr(result["timestamp"], "isoformat"):
                    result["timestamp"] = result["timestamp"].isoformat()
                elif isinstance(result["timestamp"], (int, float)):
                    from datetime import datetime

                    ts = result["timestamp"]
                    # If timestamp is > 1e10, it's likely in milliseconds
                    if ts > 1e10:
                        ts = ts / 1000
                    result["timestamp"] = datetime.fromtimestamp(ts).isoformat()
            if "created_at" in result:
                if hasattr(result["created_at"], "isoformat"):
                    result["created_at"] = result["created_at"].isoformat()
                elif isinstance(result["created_at"], (int, float)):
                    from datetime import datetime

                    ts = result["created_at"]
                    # If timestamp is > 1e10, it's likely in milliseconds
                    if ts > 1e10:
                        ts = ts / 1000
                    result["created_at"] = datetime.fromtimestamp(ts).isoformat()

            return result
        else:
            raise Error("not_found", "Backup not found")


def cleanup_old_backups():
    """
    Remove old backup records, keeping only the most recent 30 entries
    """
    with app.app_context():
        # Get the total count of backup records
        total_count = r.table("backups").count().run(db.conn)

        if total_count > 30:
            # Get the IDs of the oldest records to delete (all except the most recent 30)
            old_backup_ids = list(
                r.table("backups")
                .order_by(r.desc("timestamp"))
                .skip(30)
                .pluck("id")
                .run(db.conn)
            )

            if old_backup_ids:
                # Extract just the IDs from the result
                ids_to_delete = [backup["id"] for backup in old_backup_ids]

                # Delete the old records
                delete_result = (
                    r.table("backups").get_all(*ids_to_delete).delete().run(db.conn)
                )

                # Log the cleanup operation (optional)
                print(
                    f"Cleaned up {delete_result['deleted']} old backup records, keeping 30 most recent"
                )


def admin_backup_insert(data):
    """
    Insert a new backup record (used by backupninja service)
    """
    # Validate required fields
    required_fields = ["timestamp", "status", "type", "scope"]
    for field in required_fields:
        if field not in data:
            raise Error("bad_request", f"Missing required field: {field}")

    # Validate backup type
    if data["type"] not in ["automated", "manual"]:
        raise Error("bad_request", "Backup type must be 'automated' or 'manual'")

    # Validate backup scope
    valid_scopes = ["full", "db", "redis", "stats", "config", "disks"]
    if data["scope"] not in valid_scopes:
        raise Error(
            "bad_request", f"Backup scope must be one of: {', '.join(valid_scopes)}"
        )

    # Process details field for better structure
    if "details" in data and isinstance(data["details"], dict):
        details = data["details"]

        # Ensure checks is an array of objects with name and status
        if "checks" in details and isinstance(details["checks"], list):
            for check in details["checks"]:
                if isinstance(check, dict) and "name" in check and "status" in check:
                    # Valid check structure
                    pass
                else:
                    # Convert simple string checks to structured format
                    if isinstance(check, str):
                        check = {"name": check, "status": "success"}

        # Ensure warnings is an array
        if "warnings" in details and not isinstance(details["warnings"], list):
            details["warnings"] = [str(details["warnings"])]

        # Ensure time_breakdown is a dict
        if "time_breakdown" in details and not isinstance(
            details["time_breakdown"], dict
        ):
            details["time_breakdown"] = {}

    # Set the timestamp to current time when the record is created
    # Store the original client timestamp as backup_start_time if provided
    if "timestamp" in data:
        data["backup_start_time"] = data["timestamp"]

    # Always set timestamp to current time for uniqueness
    data["timestamp"] = r.now()

    # Add creation timestamp if not provided
    if "created_at" not in data:
        data["created_at"] = r.now()

    # Insert the backup record
    result = r.table("backups").insert(data).run(db.conn)

    if result["inserted"] == 1:
        backup_id = result["generated_keys"][0]

        # Check if we need to clean up old records (keep only last 30)
        cleanup_old_backups()

        return {
            "id": backup_id,
            "status": "success",
            "message": "Backup record created successfully",
        }
    else:
        raise Error("internal_error", "Failed to create backup record")


def admin_backup_update(backup_id, data):
    """
    Update an existing backup (deprecated - backups should be read-only)
    """
    raise Error("forbidden", "Backup records cannot be modified")


def admin_backup_delete(backup_id):
    """
    Delete a backup (deprecated - backups should be read-only)
    """
    raise Error("forbidden", "Backup records cannot be deleted")
