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

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class BackupReportRequest(BaseModel):
    """Request body for backup report submission."""

    timestamp: Any = Field(description="Backup timestamp")
    status: str = Field(description="Backup status")
    type: str = Field(description="Backup type: 'automated' or 'manual'")
    scope: str = Field(
        description="Backup scope: 'full', 'db', 'redis', 'stats', 'config', or 'disks'"
    )
    details: Optional[dict] = Field(
        default=None, description="Backup details with checks, warnings, time_breakdown"
    )
    created_at: Optional[Any] = Field(default=None, description="Creation timestamp")


class BackupIntegritySetRequest(BaseModel):
    """Request body for the weekly borg integrity check toggle."""

    integrity_enabled: bool = Field(description="Enable or disable the weekly run")


class BackupItem(BaseModel):
    """One row of ``GET /admin/backups``.

    Permissive (``ConfigDict(extra="allow")``) because legacy backup
    rows carry assorted free-form metadata in ``details`` that the
    webapp admin renders verbatim. The required fields are the ones
    the route depends on for sorting / display.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    timestamp: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    scope: Optional[str] = None
    received_at: Optional[str] = None
    created_at: Optional[str] = None
    details: Optional[dict] = None


class BackupIntegrityResponse(BaseModel):
    """Response shape for ``GET /admin/backups/integrity`` and the matching PUT."""

    integrity_enabled: bool


class BackupConfigSchedule(BaseModel):
    """Schedule hours per backup scope (``None`` = unscheduled)."""

    db: Optional[int] = None
    redis: Optional[int] = None
    stats: Optional[int] = None
    config: Optional[int] = None
    disks: Optional[int] = None


class BackupConfigEnabled(BaseModel):
    """Enabled flag per backup scope."""

    db: bool = False
    redis: bool = False
    stats: bool = False
    config: bool = False
    disks: bool = False


class BackupConfigResponse(BaseModel):
    """Response shape for ``GET /admin/backups/config``.

    Mirrors the dict returned by ``AdminBackupsService.get_backup_config``.
    """

    schedule: BackupConfigSchedule
    enabled: BackupConfigEnabled
    main_schedule_hour: int


class BackupReportInsertResponse(BaseModel):
    """Response shape for ``POST /backups`` (backupninja ingestion)."""

    id: str
    status: str
    message: str
