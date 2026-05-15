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


# =============================================================================
# STORAGE & RESOURCE ANALYTICS RESPONSES
# =============================================================================


class StorageUsageResponse(BaseModel):
    """Response shape for ``POST /analytics/storage``.

    Service ``AnalyticsProcessed.storage_usage`` always returns both
    ``media`` and ``domains`` totals in GiB."""

    media: float = Field(default=0.0, description="Total media usage (GiB)")
    domains: float = Field(
        default=0.0, description="Total per-user storage usage (GiB)"
    )


class ResourceCountResponse(BaseModel):
    """Response shape for ``POST /analytics/resources/count``.

    Service ``AnalyticsProcessed.resource_count`` writes one key per
    resource: desktops, templates, media, users, groups, deployments."""

    desktops: int = Field(default=0)
    templates: int = Field(default=0)
    media: int = Field(default=0)
    users: int = Field(default=0)
    groups: int = Field(default=0)
    deployments: int = Field(default=0)


class EmptyDeploymentRow(BaseModel):
    """One row returned by ``AnalyticsProcessed.get_empty_deployments``.

    The query ``zip``s ``deployments`` (all fields) with ``users`` plucked
    fields (``group``, ``category``, ``username``) and merges the resolved
    ``category_name`` / ``group_name`` plus the (always 0) ``domains`` count.
    Deployment columns are not pinned in the schema, so non-essential
    fields stay optional."""

    id: Optional[str] = None
    name: Optional[str] = None
    user: Optional[str] = None
    username: Optional[str] = None
    group: Optional[str] = None
    group_name: Optional[str] = None
    category: Optional[str] = None
    category_name: Optional[str] = None
    domains: int = Field(default=0, description="Number of domains attached (always 0)")


class UnusedDesktopRow(BaseModel):
    """One row returned by ``AnalyticsProcessed.get_unused_desktops``.

    Final pluck restricts output to: id, name, category_name, group_name,
    username, size."""

    id: Optional[str] = None
    name: Optional[str] = None
    category_name: Optional[str] = None
    group_name: Optional[str] = None
    username: Optional[str] = None
    size: float = Field(default=0.0, description="Storage size in GiB")


class UnusedDesktopsResult(BaseModel):
    """Wrapper produced by ``AnalyticsProcessed.get_unused_desktops``."""

    size: float = Field(default=0.0, description="Total size of unused desktops (GiB)")
    desktops: List[UnusedDesktopRow] = Field(default_factory=list)


class SuggestedRemovalsResponse(BaseModel):
    """Response shape for ``POST /analytics/suggested_removals``."""

    empty_deployments: List[EmptyDeploymentRow] = Field(default_factory=list)
    unused_desktops: UnusedDesktopsResult = Field(default_factory=UnusedDesktopsResult)


# =============================================================================
# GRAPH CONFIGURATION RESPONSES
# =============================================================================


class AnalyticsGraphConfigResponse(BaseModel):
    """Row in the ``analytics`` table — see ``AnalyticsGraphCreateRequest``
    for the writeable fields. ``id`` is auto-assigned by RethinkDB and
    ``grouping_name`` is added by the list endpoint via a join on the
    ``usage_grouping`` table; both are absent on freshly written rows."""

    id: Optional[str] = None
    name: Optional[str] = None
    grouping: Optional[str] = None
    grouping_name: Optional[str] = None
    type: Optional[str] = None
    consumer: Optional[str] = None
    item_type: Optional[str] = None


# =============================================================================
# DESKTOP ANALYTICS RESPONSES
# =============================================================================


class DesktopAnalyticsRow(BaseModel):
    """Shared row shape for the three desktop-analytics endpoints.

    ``less_used`` / ``recently_used`` produce ``last_accessed`` (and no
    ``start_count``); ``most_used`` produces ``start_count`` (and no
    ``last_accessed``). Every other column is common: identifiers, the
    backing storage join, and the GiB-normalised size."""

    desktop_id: Optional[str] = None
    desktop_status: Optional[str] = None
    desktop_category: Optional[str] = None
    storage_id: Optional[str] = None
    storage_status: Optional[str] = None
    directory_path: Optional[str] = None
    storage_path: Optional[str] = None
    size: float = Field(default=0.0, description="Storage size in GiB")
    last_accessed: Optional[Any] = Field(
        default=None,
        description="Last access time (less_used / recently_used only)",
    )
    start_count: Optional[int] = Field(
        default=None, description="Start count within window (most_used only)"
    )


# =============================================================================
# ECHART RESPONSES (non-daily views)
# =============================================================================


class EchartGroupedItem(BaseModel):
    """Row shape produced by ``get_grouped_data`` /
    ``get_grouped_unique_data`` / ``get_nested_array_grouped_data``.

    All three return ``list[{value: int, name: <group key>}]`` where
    ``name`` is the grouping value (which may be a string, int, bool,
    list of nested keys, etc., depending on the source field) and
    ``value`` is the count or distinct-count for that bucket."""

    value: int = Field(description="Count for this group")
    name: Any = Field(description="Group key — can be any JSON-serialisable value")


# Alias for the response_model on POST /admin/echart/{view} — the three
# non-daily views all yield the same row shape, so a single list type
# covers the union without per-view variants.
EchartViewResponseRow = EchartGroupedItem
