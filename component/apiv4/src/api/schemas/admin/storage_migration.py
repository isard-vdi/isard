#
#   Copyright © 2026 IsardVDI
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

"""Pydantic models for the admin storage-disk migration endpoints."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class MigrationWindowData(BaseModel):
    start: Optional[str] = None  # "HH:MM"
    end: Optional[str] = None  # "HH:MM"
    tz: str = "UTC"


class MigrationSelectionData(BaseModel):
    """What a migration job moves and where to."""

    kind: Literal["pool", "path", "category"] = "pool"
    src_pool_id: Optional[str] = None
    dst_pool_id: Optional[str] = None
    category_id: Optional[str] = None
    path_prefix: Optional[str] = None
    tree_ids: list[str] = Field(default_factory=list)


class MigrationConfigData(BaseModel):
    """Admin-set per-job knobs."""

    bwlimit_kbs: int = 0  # 0 == unlimited (rsync --bwlimit, KB/s)
    parallelism: int = 1  # concurrent independent trees
    window: Optional[MigrationWindowData] = None
    verify: bool = True  # qemu_img_check after move/rebase
    force_stop_desktops: bool = False


class MigrationPlanData(BaseModel):
    """Dry-run plan preview request — selection only, nothing is persisted."""

    selection: MigrationSelectionData


class MigrationCreateData(BaseModel):
    selection: MigrationSelectionData
    config: MigrationConfigData = Field(default_factory=MigrationConfigData)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class MigrationTreeSummary(BaseModel):
    tree_id: str
    root_storage_id: str
    derivative_templates: int = 0
    desktops: int = 0
    media: int = 0
    items_total: int = 0
    bytes_total: int = 0


class MigrationTotalsResponse(BaseModel):
    trees: int = 0
    derivative_templates: int = 0
    desktops: int = 0
    media: int = 0
    items_total: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    state_counts: dict = Field(default_factory=dict)


class MigrationPlanResponse(BaseModel):
    """Dry-run preview: what would move, grouped by root tree."""

    trees: list[MigrationTreeSummary] = Field(default_factory=list)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)


class PoolPlanResponse(BaseModel):
    """Pool-scoped aggregation for the admin overview."""

    pool_id: str
    trees: list[MigrationTreeSummary] = Field(default_factory=list)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)


class MigrationResponse(BaseModel):
    id: str
    status: str
    selection: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)
    created_by: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class MigrationListResponse(BaseModel):
    migrations: list[MigrationResponse] = Field(default_factory=list)


class MigrationStatusResponse(BaseModel):
    id: str
    status: str
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)
    state_counts: dict = Field(default_factory=dict)
    trees: list[MigrationTreeSummary] = Field(default_factory=list)
