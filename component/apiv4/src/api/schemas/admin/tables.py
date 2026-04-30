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

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class TableListRequest(BaseModel):
    """Request body for listing/filtering table items."""

    id: Optional[str] = Field(
        default=None, description="Item ID or secondary index value"
    )
    index: Optional[str] = Field(
        default=None, description="Secondary index to use with id"
    )
    order_by: Optional[str] = Field(
        default=None, description="Field to order results by"
    )
    pluck: Optional[Union[list, dict]] = Field(
        default=None, description="Fields to pluck from each item"
    )
    without: Optional[Union[list, str]] = Field(
        default=None, description="Fields to exclude from each item"
    )


class AllowedTermRequest(BaseModel):
    """Request body for searching table items by term."""

    term: str = Field(description="Search term (2+ characters)")
    category: Optional[str] = Field(default=None, description="Category to filter by")
    exclude_role: Optional[str] = Field(
        default=None, description="Role to exclude from user results"
    )
    kind: Optional[str] = Field(
        default=None, description="Media kind filter (isos, floppies)"
    )


class AllowedUpdateRequest(BaseModel):
    """Request body for updating allowed access on a table item."""

    id: str = Field(description="Item ID to update")
    allowed: dict = Field(
        description="Allowed access configuration with roles, categories, groups, users"
    )


class AllowedGetRequest(BaseModel):
    """Request body for getting allowed access list for a table item."""

    id: str = Field(description="Item ID to get allowed access for")


class TableItem(BaseModel):
    """Generic admin-table item used by ``GET`` / ``POST`` /admin/table.

    The shape is per-table (interfaces, graphics, qos, …) and the
    plucked field set varies with the request, so the model is
    permissive (``ConfigDict(extra="allow")``).
    """

    model_config = {"extra": "allow"}

    id: Optional[str] = None
