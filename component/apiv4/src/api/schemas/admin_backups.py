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

from typing import Any, Optional

from pydantic import BaseModel, Field


class BackupReportRequest(BaseModel):
    """Request body for backup report submission."""

    timestamp: Any = Field(description="Backup timestamp")
    status: str = Field(description="Backup status")
    type: str = Field(description="Backup type: 'automated' or 'manual'")
    scope: str = Field(
        description="Backup scope: 'full', 'db', 'redis', 'stats', 'config', or 'disks'"
    )
    host: Optional[str] = Field(
        default=None,
        description="Reporting host identifier; defaults to 'unknown-host' when missing",
    )
    details: Optional[dict] = Field(
        default=None, description="Backup details with checks, warnings, time_breakdown"
    )
    created_at: Optional[Any] = Field(default=None, description="Creation timestamp")


class BackupIntegritySetRequest(BaseModel):
    """Request body for the weekly borg integrity check toggle."""

    integrity_enabled: bool = Field(description="Enable or disable the weekly run")
