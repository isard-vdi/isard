#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class StorageDomain(BaseModel):
    """Domain using storage"""

    id: str
    name: str


class StorageItem(BaseModel):
    """Storage item model"""

    category: str
    domains: list[StorageDomain]
    id: str
    user_id: str
    user_name: str
    actual_size: int
    virtual_size: int
    last: int


class StorageReadyResponse(BaseModel):
    """List of ready storage items"""

    items: list[StorageItem]


class StoragePriorityResponse(BaseModel):
    """Storage priority operation response"""

    task_id: str


class TaskIdResponse(BaseModel):
    """Response containing a task ID"""

    task_id: str


class StorageCreateResponse(BaseModel):
    """Response for storage creation"""

    storage_id: str
    task_id: str


class StorageConvertResponse(BaseModel):
    """Response for storage conversion"""

    new_storage_id: str
    task_id: str


class StorageDerivativesResponse(BaseModel):
    """Response for has-derivatives check"""

    derivatives: int


class StorageParentItem(BaseModel):
    """Storage parent chain item"""

    id: str
    status: str
    parent_id: Optional[str] = None
    domains: list[dict[str, str]]


class StorageMaintenanceRequest(BaseModel):
    """Request body for setting storage to maintenance"""

    action: str = "system maintenance"


class StorageCreateRequest(BaseModel):
    """Request body for creating a new storage"""

    usage: str = Field(description="Usage: desktop, template")
    storage_type: str = Field(description="Disk format: qcow2, vmdk")
    parent: str = Field(description="Storage ID to be used as backing file")
    size: str = Field(description="Size of new storage like qemu-img command")
    user_id: Optional[str] = Field(
        default=None,
        description="User ID of the owner. If not specified, the JWT user_id is used",
    )


class StorageConvertRequest(BaseModel):
    """Request body for converting a storage"""

    new_storage_type: str = Field(description="New storage type: qcow2, vmdk, raw")
    new_storage_status: str = Field(
        default="downloadable", description="Status for the new storage"
    )
    compress: bool = Field(default=False, description="Whether to compress the output")
    priority: str = Field(default="default", description="Task priority")


class StorageRecreateRequest(BaseModel):
    """Request body for recreating a storage"""

    priority: str = Field(default="default", description="Task priority")
    retry: int = Field(default=0, description="Number of retries for the task")


class StorageMoveByPathRequest(BaseModel):
    """Request body for moving storage by path"""

    dest_path: str = Field(description="Absolute destination path")
    priority: str = Field(default="default", description="Task priority")


class StorageRsyncToPathRequest(BaseModel):
    """Request body for rsyncing storage to a path"""

    destination_path: str = Field(description="Absolute destination path")
    bwlimit: Optional[int] = Field(
        default=None, description="Bandwidth limit in KBytes/s"
    )
    remove_source_file: bool = Field(
        default=False, description="Remove source file after rsync"
    )
    priority: str = Field(default="default", description="Task priority")


class StorageRsyncToStoragePoolRequest(BaseModel):
    """Request body for rsyncing storage to a storage pool"""

    destination_storage_pool_id: str = Field(description="Destination storage pool ID")
    bwlimit: Optional[int] = Field(
        default=None, description="Bandwidth limit in KBytes/s"
    )
    remove_source_file: bool = Field(
        default=False, description="Remove source file after rsync"
    )
    priority: str = Field(default="default", description="Task priority")


class StorageVirtWinRegRequest(BaseModel):
    """Request body for applying a Windows registry patch"""

    registry_patch: str = Field(description="Registry patch content")
    retry: int = Field(default=0, description="Number of retries")


class StoragePathRequest(BaseModel):
    """Request body for set/delete path operations"""

    path: str = Field(description="File path")
    priority: str = Field(default="default", description="Task priority")
    retry: int = Field(default=0, description="Number of retries")


class StorageBatchIdsRequest(BaseModel):
    """Request body for batch operations with storage IDs"""

    ids: list[str] = Field(description="List of storage IDs")
