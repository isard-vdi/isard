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

from typing import Optional

from isardvdi_common.schemas.domains import DesktopStatusEnum
from pydantic import BaseModel, ConfigDict, Field


class StorageDomain(BaseModel):
    """Domain using storage"""

    id: str
    name: str
    status: DesktopStatusEnum


class StorageItem(BaseModel):
    """Storage item model.

    ``actual_size`` / ``virtual_size`` are populated by
    ``StorageProcessed.parse_disks`` from the row's ``qemu-img-info``
    sub-document; rows with no ``qemu-img-info`` (e.g. disks queued
    for creation, or disks whose qemu-img info hasn't been refreshed
    yet) drop the keys entirely. Likewise ``last`` is the most recent
    ``status_logs`` timestamp — disks with no status history don't
    carry it. Declaring all three required surfaced as a 500 from
    ``GET /api/v4/items/storage/get-ready`` (Bug 34) the moment the
    user table contained any such row.
    """

    category: str
    domains: list[StorageDomain]
    id: str
    user_id: str
    user_name: str
    actual_size: int | None = None
    virtual_size: int | None = None
    last: float | None = None


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


class StorageStatusLog(BaseModel):
    """A single status-log entry on a storage row"""

    status: str
    time: float


class StorageQemuImgInfo(BaseModel):
    """The ``qemu-img-info`` sub-document on a storage row.

    Stored in RethinkDB with hyphenated keys; aliased here so callers can
    populate the model from the raw row via ``**row``.
    """

    model_config = ConfigDict(populate_by_name=True)

    actual_size: Optional[int] = Field(default=None, alias="actual-size")
    virtual_size: Optional[int] = Field(default=None, alias="virtual-size")
    backing_filename: Optional[str] = Field(default=None, alias="backing-filename")
    full_backing_filename: Optional[str] = Field(
        default=None, alias="full-backing-filename"
    )
    cluster_size: Optional[int] = Field(default=None, alias="cluster-size")
    dirty_flag: Optional[bool] = Field(default=None, alias="dirty-flag")
    filename: Optional[str] = None
    format: Optional[str] = None


class StoragesWithUuidEntry(BaseModel):
    """Phantom-storage diagnostic entry.

    Shape produced when a ``find`` task discovers extra files matching
    a storage UUID (see the ``handle_storage_update_pool`` body in
    ``change-handler/.../task_results/storage.py``):
    ``{"status": ..., "path": ...}`` per row, with ``id`` merged in by
    the global aggregation queries (``get_storages_with_uuid``) and
    ``count`` returned instead of ``path`` by the per-status grouping
    query (``get_storages_with_uuid_status``). One model serves all
    four endpoints; only ``status`` is universal.
    """

    status: str
    path: Optional[str] = None
    id: Optional[str] = None
    count: Optional[int] = None


class StorageDetailResponse(BaseModel):
    """Raw storage row returned by ``GET /item/storage/{storage_id}``.

    Mirrors the well-known columns of the ``storage`` RethinkDB table.
    Unknown extras are dropped (default ``extra='ignore'``); the
    hyphenated ``qemu-img-info`` key is aliased so the model can be
    instantiated directly from the raw row.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: Optional[str] = None
    status: Optional[str] = None
    directory_path: Optional[str] = None
    parent: Optional[str] = None
    user_id: Optional[str] = None
    perms: Optional[list[str]] = None
    status_logs: Optional[list[StorageStatusLog]] = None
    task: Optional[str] = None
    qemu_img_info: Optional[StorageQemuImgInfo] = Field(
        default=None, alias="qemu-img-info"
    )
    storages_with_uuid: Optional[list[StoragesWithUuidEntry]] = None
