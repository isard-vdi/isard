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

from isardvdi_common.schemas.usage import UsageRetentionConfig  # noqa: F401
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


# =============================================================================
# RETENTION — schema lives in _common.schemas.usage so the offline
# rollup script (engine/scripts/rollup_usage_consumption.py) can
# validate the same contract without depending on apiv4.
# =============================================================================


# =============================================================================
# RESPONSE MODELS
#
# Row shapes are derived from the underlying ``isardvdi_common.lib.usage``
# layer (see services/admin/usage.py). CRUD groups reuse a single row
# model for their list/get endpoints; create/update/delete service calls
# return ``True`` and the route coerces to ``{}``, so those endpoints use
# ``EmptyResponse`` from ``api.schemas.common``.
# =============================================================================


class UsageItemConsumption(BaseModel):
    """A single ``(date, item)`` consumption row used by the consumption
    list and the start/end comparison endpoints.

    ``inc`` and ``abs`` are dicts keyed by parameter id (``{param_id:
    float}``) and vary in shape with the requested ``grouping_params``,
    so they are typed permissively as ``Dict[str, Any]``.
    """

    name: Optional[str] = Field(default=None, description="Item name")
    date: Optional[Any] = Field(
        default=None,
        description="Bucket date (datetime or date string).",
    )
    inc: Dict[str, Any] = Field(
        default_factory=dict, description="Per-parameter increment values."
    )
    abs: Dict[str, Any] = Field(
        default_factory=dict, description="Per-parameter absolute values."
    )
    item_id: Optional[str] = Field(default=None, description="Item ID")
    item_name: Optional[str] = Field(default=None, description="Item name")
    item_type: Optional[str] = Field(default=None, description="Item type")
    item_consumer: Optional[str] = Field(default=None, description="Consumer type")
    granularity: Optional[str] = Field(
        default=None,
        description="Bucket granularity tier (daily / weekly / monthly).",
    )


class UsageStartEndItemResponse(BaseModel):
    """Row of the start/end consumption comparison list."""

    item_id: str = Field(description="Item ID")
    item_name: str = Field(description="Item name")
    item_description: str = Field(description="Item description")
    item_consumer: Optional[str] = Field(default=None, description="Consumer type")
    start: UsageItemConsumption = Field(
        description="Consumption snapshot at the window start."
    )
    end: UsageItemConsumption = Field(
        description="Consumption snapshot at the window end."
    )
    duplicated_item_id: bool = Field(
        description="Whether this item id appears more than once in the result."
    )


class UsageConsumersCountResponse(BaseModel):
    """Count of rows in the ``usage_consumption`` table."""

    count: int = Field(description="Total consumption rows.")


class UsageDistinctItemResponse(BaseModel):
    """Distinct-item dropdown row from the ``item_consumer`` index."""

    item_id: str = Field(description="Item ID")
    item_name: Optional[str] = Field(default=None, description="Item name")
    category_name: Optional[str] = Field(
        default=None, description="Category name (joined from ``categories``)."
    )
    username: Optional[str] = Field(
        default=None,
        description="Owner username when the consumer is desktop/template.",
    )
    item_consumer_category_id: Optional[str] = Field(
        default=None,
        description="Consumer category id (only present when filtered).",
    )


class UsageParameterResponse(BaseModel):
    """Row of the ``usage_parameter`` table."""

    id: str = Field(description="Parameter ID")
    name: str = Field(description="Parameter name")
    desc: Optional[str] = Field(default=None, description="Parameter description")
    custom: bool = Field(description="Whether this is a custom parameter")
    default: Optional[float] = Field(
        default=None, description="Default value for the parameter."
    )
    formula: Optional[str] = Field(default=None, description="Parameter formula")
    item_type: str = Field(description="Item type this parameter applies to")
    units: Optional[str] = Field(default=None, description="Parameter units")


class UsageLimitValuesResponse(BaseModel):
    """Validated limit values stored on a ``usage_limit`` row."""

    hard: float = Field(description="Hard limit value")
    soft: float = Field(description="Soft limit value")
    exp_min: float = Field(description="Expected minimum value")
    exp_max: float = Field(description="Expected maximum value")


class UsageLimitResponse(BaseModel):
    """Row of the ``usage_limit`` table."""

    id: Optional[str] = Field(default=None, description="Limit ID")
    name: str = Field(description="Limit name")
    desc: Optional[str] = Field(default=None, description="Limit description")
    limits: UsageLimitValuesResponse = Field(description="Limit values")


class UsageGroupingResponse(BaseModel):
    """Row of the ``usage_grouping`` table or a synthetic system grouping."""

    id: str = Field(description="Grouping ID")
    name: str = Field(description="Grouping name")
    desc: Optional[str] = Field(default=None, description="Grouping description")
    item_type: str = Field(description="Item type")
    item_sub_type: Optional[str] = Field(
        default=None,
        description="System pseudo-grouping kind (all / system / custom).",
    )
    parameters: List[str] = Field(
        default_factory=list, description="Parameter IDs in this grouping."
    )


class UsageGroupingsDropdownResponse(BaseModel):
    """Dropdown shape for ``/admin/usage/groupings_dropdown``.

    Inner dicts are keyed by item_type (``desktop``/``media``/``storage``/
    ``user``) and carry the system pseudo-groupings + the user-defined
    rows for that item type.
    """

    system: Dict[str, List[UsageGroupingResponse]] = Field(default_factory=dict)
    custom: Dict[str, List[UsageGroupingResponse]] = Field(default_factory=dict)


class UsageCreditResponse(BaseModel):
    """Row of the ``usage_credit`` table.

    The list endpoint merges ``category_name``/``item_description``/
    ``grouping_name`` onto the row; the by-id endpoint omits them — both
    are declared optional here so the same model serves both.
    """

    id: Optional[str] = Field(default=None, description="Credit ID")
    item_id: str = Field(description="Item ID")
    item_consumer: Optional[str] = Field(default=None, description="Consumer type")
    item_type: str = Field(description="Item type")
    grouping_id: str = Field(description="Grouping ID")
    start_date: Optional[Any] = Field(
        default=None, description="Credit start (datetime or string)."
    )
    end_date: Optional[Any] = Field(
        default=None, description="Credit end (datetime or string, may be null)."
    )
    limits: Optional[UsageLimitValuesResponse] = Field(
        default=None, description="Denormalised limit values."
    )
    limits_id: Optional[str] = Field(default=None, description="Source limit id.")
    limits_name: Optional[str] = Field(default=None, description="Source limit name.")
    limits_desc: Optional[str] = Field(
        default=None, description="Source limit description."
    )
    category_name: Optional[str] = Field(
        default=None,
        description="Category name (joined; only on the list endpoint).",
    )
    item_description: Optional[str] = Field(
        default=None,
        description="Item description (joined; only on the list endpoint).",
    )
    grouping_name: Optional[str] = Field(
        default=None,
        description="Grouping name (joined; only on the list endpoint).",
    )


class UsageCreditIntervalResponse(BaseModel):
    """Slice of the credit timeline returned by ``find_in_period``.

    The endpoint produces a chain of ``before``/``inner``/``after``
    intervals; intervals without an active credit carry ``limits=None``
    and just bracket the dates of the gap.
    """

    id: Optional[str] = Field(default=None, description="Credit ID, when present")
    item_id: Optional[str] = Field(default=None, description="Item ID")
    item_consumer: Optional[str] = Field(default=None, description="Consumer type")
    item_type: Optional[str] = Field(default=None, description="Item type")
    grouping_id: Optional[str] = Field(default=None, description="Grouping ID")
    start_date: str = Field(description="Interval start (string).")
    end_date: str = Field(description="Interval end (string).")
    limits: Optional[UsageLimitValuesResponse] = Field(
        default=None,
        description="Limit values for the interval; ``None`` for gap rows.",
    )
    limits_id: Optional[str] = Field(default=None)
    limits_name: Optional[str] = Field(default=None)
    limits_desc: Optional[str] = Field(default=None)


class UsageUnifyItemNameResponse(BaseModel):
    """Response for ``/admin/usage/unify/{item_id}/item_name``."""

    name: str = Field(description="Resolved canonical item name.")


class UsageOverlappingResponse(BaseModel):
    """Response for ``/admin/usage/check/overlapping/...``.

    ``check_overlapping`` returns ``None`` (no conflict) or a descriptor
    of the conflicting credit and the trim/delete action; ``None`` is
    coerced to ``{}`` by the route, so every field is optional.
    """

    credit_id: Optional[str] = Field(
        default=None, description="The conflicting credit's id."
    )
    action: Optional[str] = Field(
        default=None,
        description="Reconciliation verb (``cut`` or ``deleted``).",
    )
    start_date: Optional[Any] = Field(
        default=None,
        description="New start_date when ``action='cut'`` and the tail moves.",
    )
    end_date: Optional[Any] = Field(
        default=None,
        description="New end_date when ``action='cut'`` and the head moves.",
    )
