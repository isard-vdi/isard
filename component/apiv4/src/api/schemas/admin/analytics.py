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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# ANALYTICS RESOURCE REQUESTS
# =============================================================================


class AnalyticsCategoriesRequest(BaseModel):
    """Request body for analytics endpoints that filter by categories."""

    categories: Optional[List[str]] = Field(
        default=None, description="List of category IDs to filter"
    )


class AnalyticsSuggestedRemovalsRequest(BaseModel):
    """Request body for suggested removals endpoint."""

    categories: Optional[List[str]] = Field(
        default=None, description="List of category IDs to filter"
    )
    months_without_use: int = Field(
        description="Number of months without use to consider for removal"
    )


# =============================================================================
# GRAPH CONFIGURATION
# =============================================================================


class AnalyticsGraphCreateRequest(BaseModel):
    """Request body for creating an analytics graph configuration."""

    name: Optional[str] = Field(default=None, description="Graph name")
    grouping: Optional[str] = Field(default=None, description="Grouping ID")
    type: Optional[str] = Field(default=None, description="Graph type")
    consumer: Optional[str] = Field(default=None, description="Consumer type")
    item_type: Optional[str] = Field(default=None, description="Item type")


class AnalyticsGraphUpdateRequest(BaseModel):
    """Request body for updating an analytics graph configuration."""

    name: Optional[str] = Field(default=None, description="Graph name")
    grouping: Optional[str] = Field(default=None, description="Grouping ID")
    type: Optional[str] = Field(default=None, description="Graph type")
    consumer: Optional[str] = Field(default=None, description="Consumer type")
    item_type: Optional[str] = Field(default=None, description="Item type")


# =============================================================================
# DESKTOP ANALYTICS
# =============================================================================


class DesktopAnalyticsRequest(BaseModel):
    """Request body for desktop analytics endpoints."""

    days_before: int = Field(default=30, description="Number of days to look back")
    limit: int = Field(default=10, description="Maximum number of results")
    not_in_directory_path: Optional[str] = Field(
        default=None, description="Skip desktops with this directory path prefix"
    )
    status: Optional[str] = Field(default=None, description="Filter by desktop status")


# =============================================================================
# ECHART REQUESTS
# =============================================================================


class EchartRequest(BaseModel):
    """Request body for echart data endpoints."""

    table: str = Field(description="Database table name")
    date_field: Optional[str] = Field(
        default=None, description="Date field for daily items"
    )
    group_field: Optional[str] = Field(default=None, description="Field to group by")
    unique_field: Optional[str] = Field(
        default=None, description="Field for unique counting"
    )
    nested_array_field: Optional[str] = Field(
        default=None, description="Nested array field name"
    )


class EchartDailyItemsResponse(BaseModel):
    """Response shape for ``POST /admin/echart/daily_items``.

    The service returns ``{x: [iso-dates], series: {<date_field>: [counts]}}``
    matching the eChart contract — a single dict, not a list. The
    other ``echart`` views return ``list[{value, name}]``; this is
    why daily_items has its own route + response model."""

    x: list[str] = Field(default_factory=list)
    series: dict[str, list[int]] = Field(default_factory=dict)
