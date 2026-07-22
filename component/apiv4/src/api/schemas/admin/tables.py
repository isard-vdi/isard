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
    # TODO: Standarize pluck/without across all table endpoints to use the same format (e.g. list of strings)
    pluck: Optional[Union[list, dict, str]] = Field(
        default=None, description="Fields to pluck from each item"
    )
    without: Optional[Union[list, dict, str]] = Field(
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

    id: str | int = Field(description="Item ID to get allowed access for")


class TableItem(BaseModel):
    """Generic admin-table item used by ``GET`` / ``POST`` /admin/items/table.

    The shape is per-table (interfaces, graphics, qos, …) and the
    plucked field set varies with the request, so the model is
    permissive (``ConfigDict(extra="allow")``).

    ``id`` accepts both ``str`` and ``int`` because RethinkDB's
    ``config`` singleton row is stored with ``id=1`` (integer), and
    the same admin route serves every table — see
    ``Pydantic model vs DB convention`` recurring pattern in the
    apiv4-migration skill: DB conventions use sentinel types
    (``False`` / ``int`` / ``None``); Pydantic models added later
    must accept them rather than forcing the DB to change shape.
    """

    model_config = {"extra": "allow"}

    id: Optional[Union[str, int]] = None


class AllowedTermItem(BaseModel):
    """Single autocomplete row returned by
    ``POST /admin/allowed/term/{table}``.

    The service overrides the pluck per-table:
    ``users`` adds ``uid, role, username, category_name, group_name``;
    ``groups`` adds ``parent_category, category_name``. The webapp's
    select2 templates render those fields (e.g.
    ``static/js/snippets/alloweds.js`` shows
    ``item.name [item.uid] (item.category_name)``), so the model must
    let them pass through — ``extra='allow'`` preserves them; without
    it Pydantic strips every field except ``id``/``name`` and the
    select2 labels become ``undefined``.
    """

    model_config = {"extra": "allow"}

    id: str
    name: Optional[str] = None


class AllowedTableUserItem(BaseModel):
    """Enriched user row from ``Alloweds.get_allowed`` — pluck'd to
    ``id, name, uid, username, photo`` and merged with
    ``category_name``/``group_name``."""

    id: str
    name: Optional[str] = None
    uid: Optional[str] = None
    username: Optional[str] = None
    photo: Optional[str] = None
    group_name: Optional[str] = None
    category_name: Optional[str] = None


class AllowedTableGroupItem(BaseModel):
    """Enriched group row from ``Alloweds.get_allowed`` — pluck'd to
    ``id, name, uid, parent_category`` and merged with ``category_name``."""

    id: str
    name: Optional[str] = None
    uid: Optional[str] = None
    parent_category: Optional[str] = None
    category_name: Optional[str] = None


class AllowedTableEntityItem(BaseModel):
    """Enriched roles/categories row from ``Alloweds.get_allowed`` —
    pluck'd to ``id, name, uid, parent_category``."""

    id: str
    name: Optional[str] = None
    uid: Optional[str] = None
    parent_category: Optional[str] = None


class AllowedTableResponse(BaseModel):
    """Response model for ``POST /allowed/table/{table}``.

    Mirrors the dict returned by ``Alloweds.get_allowed`` — each
    bucket is either ``False`` (allow-none) or a list of enriched
    rows. Buckets are individually optional because the underlying
    ``allowed`` dict may not declare every key on legacy rows.
    """

    roles: Optional[Union[bool, list[AllowedTableEntityItem]]] = None
    categories: Optional[Union[bool, list[AllowedTableEntityItem]]] = None
    groups: Optional[Union[bool, list[AllowedTableGroupItem]]] = None
    users: Optional[Union[bool, list[AllowedTableUserItem]]] = None
