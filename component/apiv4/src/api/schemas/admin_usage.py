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
# CONSUMPTION
# =============================================================================


class UsageConsumptionRequest(BaseModel):
    """Request body for usage consumption between dates."""

    start_date: Optional[str] = Field(
        default=None, description="Start date in YYYY-MM-DD format"
    )
    end_date: Optional[str] = Field(
        default=None, description="End date in YYYY-MM-DD format"
    )
    items_ids: Optional[List[str]] = Field(
        default=None, description="List of item IDs to filter"
    )
    item_ids: Optional[List[str]] = Field(
        default=None, description="List of item IDs for ownership checks"
    )
    item_type: Optional[str] = Field(default=None, description="Type of item")
    grouping: Optional[List[str]] = Field(
        default=None, description="Grouping parameters"
    )


class UsageStartEndRequest(BaseModel):
    """Request body for start/end consumption."""

    start_date: Optional[str] = Field(
        default=None, description="Start date in YYYY-MM-DD format"
    )
    end_date: Optional[str] = Field(
        default=None, description="End date in YYYY-MM-DD format"
    )
    items_ids: Optional[List[str]] = Field(
        default=None, description="List of item IDs to filter"
    )
    item_ids: Optional[List[str]] = Field(
        default=None, description="List of item IDs for ownership checks"
    )
    item_type: Optional[str] = Field(default=None, description="Type of item")
    item_consumer: Optional[str] = Field(
        default=None, description="Consumer type (e.g. category, hypervisor)"
    )
    grouping: Optional[List[str]] = Field(
        default=None, description="Grouping parameters"
    )


# =============================================================================
# PARAMETERS
# =============================================================================


class UsageParameterIdsRequest(BaseModel):
    """Request body for listing usage parameters by IDs."""

    ids: Optional[List[str]] = Field(default=None, description="List of parameter IDs")


class UsageParameterCreateRequest(BaseModel):
    """Request body for creating a usage parameter."""

    id: str = Field(description="Parameter ID")
    name: str = Field(description="Parameter name")
    desc: str = Field(description="Parameter description")
    custom: bool = Field(description="Whether this is a custom parameter")
    formula: str = Field(description="Parameter formula")
    item_type: str = Field(description="Item type this parameter applies to")
    units: str = Field(description="Parameter units")


class UsageParameterUpdateRequest(BaseModel):
    """Request body for updating a usage parameter."""

    id: str = Field(description="Parameter ID")
    name: Optional[str] = Field(default=None, description="Parameter name")
    desc: Optional[str] = Field(default=None, description="Parameter description")
    custom: bool = Field(description="Whether this is a custom parameter")
    formula: Optional[str] = Field(default=None, description="Parameter formula")
    item_type: Optional[str] = Field(
        default=None, description="Item type this parameter applies to"
    )
    units: Optional[str] = Field(default=None, description="Parameter units")


# =============================================================================
# LIMITS
# =============================================================================


class UsageLimitsValues(BaseModel):
    """Limits values."""

    hard: float = Field(description="Hard limit value")
    soft: float = Field(description="Soft limit value")
    exp_min: float = Field(description="Expected minimum value")
    exp_max: float = Field(description="Expected maximum value")


class UsageLimitCreateRequest(BaseModel):
    """Request body for creating a usage limit."""

    name: str = Field(description="Limit name")
    desc: str = Field(description="Limit description")
    limits: UsageLimitsValues = Field(description="Limit values")


class UsageLimitUpdateRequest(BaseModel):
    """Request body for updating a usage limit."""

    name: str = Field(description="Limit name")
    desc: str = Field(description="Limit description")
    limits: UsageLimitsValues = Field(description="Limit values")


# =============================================================================
# GROUPINGS
# =============================================================================


class UsageGroupingCreateRequest(BaseModel):
    """Request body for creating a usage grouping."""

    name: str = Field(description="Grouping name")
    desc: Optional[str] = Field(default=None, description="Grouping description")
    item_type: str = Field(description="Item type")
    parameters: List[str] = Field(description="List of parameter IDs")


class UsageGroupingUpdateRequest(BaseModel):
    """Request body for updating a usage grouping."""

    id: str = Field(description="Grouping ID")
    name: Optional[str] = Field(default=None, description="Grouping name")
    desc: Optional[str] = Field(default=None, description="Grouping description")
    item_type: Optional[str] = Field(default=None, description="Item type")
    parameters: Optional[List[str]] = Field(
        default=None, description="List of parameter IDs"
    )


# =============================================================================
# CREDITS
# =============================================================================


class UsageCreditCreateRequest(BaseModel):
    """Request body for creating a usage credit."""

    item_ids: List[str] = Field(description="List of item IDs")
    item_consumer: str = Field(description="Consumer type")
    item_type: str = Field(description="Item type")
    grouping_id: str = Field(description="Grouping ID")
    limit_id: str = Field(description="Limit ID")
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(
        default=None, description="End date in YYYY-MM-DD format (null for no end)"
    )


class UsageCreditUpdateRequest(BaseModel):
    """Request body for updating a usage credit."""

    id: str = Field(description="Credit ID")
    item_id: Optional[str] = Field(default=None, description="Item ID")
    item_type: Optional[str] = Field(default=None, description="Item type")
    grouping_id: Optional[str] = Field(default=None, description="Grouping ID")
    start_date: Optional[str] = Field(default=None, description="Start date")
    end_date: Optional[str] = Field(default=None, description="End date")
    limits: Optional[Dict[str, Any]] = Field(default=None, description="Limit values")


# =============================================================================
# RESET DATES
# =============================================================================


class UsageResetDatesRequest(BaseModel):
    """Request body for adding reset dates."""

    date_list: List[str] = Field(description="List of dates in MM/DD/YYYY format")
