#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Optional

from pydantic import BaseModel, Field


class StoragePoolCreateRequest(BaseModel):
    """Request body for creating a storage pool"""

    id: Optional[str] = None
    name: str
    description: str
    mountpoint: str
    enabled: bool
    categories: list[str] = []
    paths: Optional[dict[str, list[dict[str, Any]]]] = None
    allowed: Optional[dict[str, Any]] = None
    read: Optional[bool] = None
    write: Optional[bool] = None
    startable: Optional[bool] = None
    unused_desktops_cutoff_time: Optional[int] = None
    qos_disk_id: Optional[str] = None


class StoragePoolUpdateRequest(BaseModel):
    """Request body for updating a storage pool"""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    mountpoint: Optional[str] = None
    enabled: Optional[bool] = None
    enabled_virt: Optional[bool] = None
    categories: Optional[list[str]] = None
    paths: Optional[dict[str, list[dict[str, Any]]]] = None
    allowed: Optional[dict[str, Any]] = None
    read: Optional[bool] = None
    write: Optional[bool] = None
    startable: Optional[bool] = None
    unused_desktops_cutoff_time: Optional[int] = None
    qos_disk_id: Optional[str] = None


class StoragePoolResponse(BaseModel):
    """Response model for a storage pool"""

    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    mountpoint: Optional[str] = None
    enabled: Optional[bool] = None
    enabled_virt: Optional[bool] = None
    categories: Optional[list[str]] = None
    paths: Optional[dict[str, Any]] = None
    allowed: Optional[dict[str, Any]] = None
    read: Optional[bool] = None
    write: Optional[bool] = None
    startable: Optional[bool] = None
    unused_desktops_cutoff_time: Optional[int] = None
    is_default: Optional[bool] = None
    categories_names: Optional[list[dict[str, str]]] = None
    storages: Optional[int] = None
    hypers: Optional[int] = None
    qos_disk_id: Optional[str] = None


class StoragePoolListResponse(BaseModel):
    """Response model for a list of storage pools"""

    storage_pools: list[StoragePoolResponse]


class StoragePoolByPathRequest(BaseModel):
    """Request body for getting a storage pool by path"""

    path: str


class CheckCategoryAvailabilityRequest(BaseModel):
    """Request body for checking category availability"""

    categories: list[str]
    storage_pool_id: Optional[str] = None


class CheckCategoryAvailabilityResponse(BaseModel):
    """Response model for category availability check"""

    available: bool
