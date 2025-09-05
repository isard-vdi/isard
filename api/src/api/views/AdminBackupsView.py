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
import re

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_backups import admin_backup_get, admin_backup_insert, admin_backup_list
from .decorators import is_admin


@app.route("/api/v3/admin/backups", methods=["GET"])
@is_admin
def api_v3_admin_backups(payload):
    """
    Backup management endpoint for administrators (read-only)
    """
    options = request.args

    if options.get("id"):
        result = admin_backup_get(options.get("id"), pluck=options.get("pluck"))
    else:
        result = admin_backup_list()

    return result


@app.route("/api/v3/admin/backups/<backup_id>", methods=["GET"])
@is_admin
def api_v3_admin_backup(payload, backup_id):
    """
    Individual backup view endpoint (read-only)
    """
    result = admin_backup_get(backup_id)
    return result


@app.route("/api/v3/backups", methods=["POST"])
@is_admin
def api_v3_backup_report(payload):
    """
    Endpoint for backupninja to send backup reports
    This endpoint accepts backup reports from the backup service
    """
    try:
        data = request.get_json(force=True)
        result = admin_backup_insert(data)
        return result
    except Exception as e:
        raise Error("bad_request", "Invalid backup report data: " + str(e))


@app.route("/api/v3/admin/backups/config", methods=["GET"])
@is_admin
def api_v3_admin_backup_config(payload):
    """
    Get backup configuration from environment variables
    """

    def parse_backup_schedule(schedule_env):
        """Parse backup schedule from environment variable like 'everyday at 19'"""
        if not schedule_env:
            return None

        # Match patterns like "everyday at 19" or "everyday at 19:00"
        match = re.search(r"at\s+(\d{1,2})(?::\d{2})?", schedule_env)
        if match:
            return int(match.group(1))
        return None

    # Get backup schedule from environment variables
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

    # Get the most common schedule hour as the main schedule
    schedule_hours = [h for h in config["schedule"].values() if h is not None]
    if schedule_hours:
        config["main_schedule_hour"] = max(
            set(schedule_hours), key=schedule_hours.count
        )
    else:
        config["main_schedule_hour"] = 19  # Default to 19:00

    return config
