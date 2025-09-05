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

from flask import jsonify
from flask_login import login_required

from webapp import app

from .decorators import isAdmin

# Create webapp-based API endpoints that return test data
# These will be replaced with proper API proxy once connectivity is fixed


@app.route("/api/v3/admin/backups", methods=["GET"])
@login_required
@isAdmin
def webapp_api_admin_backups():
    """
    Backup data endpoint - temporary test data
    """
    return jsonify(
        [
            {
                "id": "backup-2025-09-06-19-00",
                "timestamp": "2025-09-06T19:00:00Z",
                "type": "automated",
                "status": "SUCCESS",
                "scope": "all",
                "duration": 45,
                "summary": "Daily backup completed successfully",
                "total_actions": 12,
                "successful_actions": 12,
                "warning_actions": 0,
                "failed_actions": 0,
                "fatal_actions": 0,
                "filesystem_metrics": {
                    "usage": {
                        "backup_storage": {
                            "used": "2.8G",
                            "size": "41G",
                            "usage_percent": 7,
                            "available": "38.2G",
                            "device": "/dev/sda1",
                            "mount_point": "/opt/isard-local/backup",
                        }
                    }
                },
                "backup_types": {
                    "db": {
                        "total_actions": 3,
                        "successful": 3,
                        "errors": 0,
                        "warnings": 0,
                        "total_duration": 15,
                    },
                    "redis": {
                        "total_actions": 2,
                        "successful": 2,
                        "errors": 0,
                        "warnings": 0,
                        "total_duration": 8,
                    },
                    "config": {
                        "total_actions": 4,
                        "successful": 4,
                        "errors": 0,
                        "warnings": 0,
                        "total_duration": 12,
                    },
                    "stats": {
                        "total_actions": 3,
                        "successful": 3,
                        "errors": 0,
                        "warnings": 0,
                        "total_duration": 10,
                    },
                },
            },
            {
                "id": "backup-2025-09-05-19-00",
                "timestamp": "2025-09-05T19:00:00Z",
                "type": "automated",
                "status": "SUCCESS",
                "scope": "all",
                "duration": 42,
                "summary": "Daily backup completed successfully",
                "total_actions": 12,
                "successful_actions": 12,
                "warning_actions": 0,
                "failed_actions": 0,
                "fatal_actions": 0,
            },
            {
                "id": "backup-2025-09-04-19-00",
                "timestamp": "2025-09-04T19:00:00Z",
                "type": "automated",
                "status": "PARTIAL",
                "scope": "all",
                "duration": 38,
                "summary": "Backup completed with warnings",
                "total_actions": 12,
                "successful_actions": 10,
                "warning_actions": 2,
                "failed_actions": 0,
                "fatal_actions": 0,
            },
        ]
    )


@app.route("/api/v3/admin/backups/config", methods=["GET"])
@login_required
@isAdmin
def webapp_api_admin_backups_config():
    """
    Backup configuration endpoint - temporary test data
    """
    return jsonify(
        {
            "schedule": {
                "db": 19,
                "redis": 19,
                "stats": 19,
                "config": 19,
                "disks": None,
            },
            "enabled": {
                "db": True,
                "redis": True,
                "stats": True,
                "config": True,
                "disks": False,
            },
            "main_schedule_hour": 19,
        }
    )


@app.route("/api/v3/admin/backups/<backup_id>", methods=["GET"])
@login_required
@isAdmin
def webapp_api_admin_backup_details(backup_id):
    """
    Individual backup details endpoint - temporary test data
    """
    return jsonify(
        {
            "id": backup_id,
            "timestamp": "2025-09-06T19:00:00Z",
            "type": "automated",
            "status": "SUCCESS",
            "scope": "all",
            "duration": 45,
            "summary": "Daily backup completed successfully",
            "total_actions": 12,
            "successful_actions": 12,
            "warning_actions": 0,
            "failed_actions": 0,
            "fatal_actions": 0,
            "filesystem_metrics": {
                "usage": {
                    "backup_storage": {
                        "used": "2.8G",
                        "size": "41G",
                        "usage_percent": 7,
                        "available": "38.2G",
                        "device": "/dev/sda1",
                        "mount_point": "/opt/isard-local/backup",
                    }
                }
            },
            "backup_types": {
                "db": {
                    "total_actions": 3,
                    "successful": 3,
                    "errors": 0,
                    "warnings": 0,
                    "total_duration": 15,
                    "borg_statistics": {
                        "file_count": 2834,
                        "original_size": "156MB",
                        "compressed_size": "89MB",
                        "deduplicated_size": "45MB",
                        "unique_chunks": 234,
                        "total_chunks": 456,
                    },
                },
                "redis": {
                    "total_actions": 2,
                    "successful": 2,
                    "errors": 0,
                    "warnings": 0,
                    "total_duration": 8,
                    "borg_statistics": {
                        "file_count": 1234,
                        "original_size": "5.2MB",
                        "compressed_size": "3.1MB",
                        "deduplicated_size": "2.8MB",
                        "unique_chunks": 45,
                        "total_chunks": 67,
                    },
                },
                "config": {
                    "total_actions": 4,
                    "successful": 4,
                    "errors": 0,
                    "warnings": 0,
                    "total_duration": 12,
                    "borg_statistics": {
                        "file_count": 567,
                        "original_size": "12MB",
                        "compressed_size": "8MB",
                        "deduplicated_size": "6MB",
                        "unique_chunks": 89,
                        "total_chunks": 123,
                    },
                },
                "stats": {
                    "total_actions": 3,
                    "successful": 3,
                    "errors": 0,
                    "warnings": 0,
                    "total_duration": 10,
                    "borg_statistics": {
                        "file_count": 3456,
                        "original_size": "234MB",
                        "compressed_size": "145MB",
                        "deduplicated_size": "98MB",
                        "unique_chunks": 567,
                        "total_chunks": 890,
                    },
                },
            },
            "actions": [
                {"name": "backup-db-dump", "status": "SUCCESS", "duration": 8},
                {"name": "backup-db-borg", "status": "SUCCESS", "duration": 7},
                {"name": "backup-redis-info", "status": "SUCCESS", "duration": 2},
                {"name": "backup-redis-borg", "status": "SUCCESS", "duration": 6},
                {"name": "backup-config-collect", "status": "SUCCESS", "duration": 3},
                {"name": "backup-config-borg", "status": "SUCCESS", "duration": 9},
                {"name": "backup-stats-export", "status": "SUCCESS", "duration": 5},
                {"name": "backup-stats-borg", "status": "SUCCESS", "duration": 5},
            ],
        }
    )
