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

from typing import Optional

from pydantic import BaseModel, Field


class AdminStorageFilterRequest(BaseModel):
    """Request body for filtering admin storage listings."""

    categories: Optional[list[str]] = Field(
        default=None, description="Category IDs to filter by (admin only)"
    )


class AdminStorageStatusCount(BaseModel):
    """One row of ``GET /storage/status``: ``{status, count}``."""

    status: str
    count: int


class AdminStorageItem(BaseModel):
    """One row of ``GET /admin/items/storage`` and the by-status / by-role
    variants. Permissive (``ConfigDict(extra="allow")``) because the
    storage doc carries varied per-status fields the webapp admin
    renders verbatim.
    """

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    user_id: Optional[str] = None
    category: Optional[str] = None


class AdminStorageDomain(BaseModel):
    """One row of ``GET /admin/items/storage/domains/{id}`` and
    ``GET /admin/items/media/domains/{id}``: the domain id + display name
    the webapp admin lists. Permissive — joined fields differ.
    """

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    name: Optional[str] = None


class AdminStorageInfo(BaseModel):
    """Response shape for ``GET /admin/item/storage/info/{id}`` and
    ``GET /admin/item/storage/search-info/{id}``.

    Backed by ``AdminStorageService.get_storage_info`` /
    ``get_storage_search_info`` — qemu-img blob plus owner joins.
    Permissive because those service methods merge sub-objects whose
    keys differ per backend.
    """

    model_config = {"extra": "allow"}
