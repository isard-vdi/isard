#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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

from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from ..bookings import Reservables


class Disk(BaseModel):
    storage_id: Optional[str] = None
    bus: Optional[str] = None
    extension: Optional[str] = None
    parent: Optional[str] = None

    @field_validator("bus", mode="before")
    @classmethod
    def _normalise_bus(cls, value: Any) -> Any:
        # Historical desktops persisted ``bus: False`` (raw bool) in
        # their ``create_dict.hardware.disks[]``. The deployment-edit
        # revalidation through ``DeploymentUpdateModel`` would then
        # 500 because the strict ``Optional[str]`` rejects bool.
        # Map ``False`` → ``None`` here so legacy rows survive the
        # round-trip without rewriting the stored data.
        if value is False:
            return None
        return value


class Iso(BaseModel):
    id: str


class Interface(BaseModel):
    id: str
    mac: str


class Hardware(BaseModel):
    virtualization_nested: bool = False
    boot_order: Optional[list[Literal["iso", "floppy", "disk", "pxe"]]] = ["disk"]
    qos_disk_id: Optional[str | bool] = False
    vcpus: int
    memory: float
    graphics: list[str] = []
    videos: list[str]
    interfaces: list[str] | list[Interface]
    disk_bus: Literal["default", "ide", "sata", "virtio"] = "default"
    isos: Optional[list[Iso]] = []
    floppies: list[Iso] = []
    disks: Optional[list[Disk]] = None


class GuestProperties(BaseModel):
    class _GuestPropertiesCredentials(BaseModel):
        username: str = "isard"
        password: str = "pirineus"

    class _GuestPropertiesViewers(BaseModel):
        browser_rdp: dict | None | MISSING = MISSING
        browser_vnc: dict | None | MISSING = MISSING
        file_rdpgw: dict | None | MISSING = MISSING
        file_rdpvpn: dict | None | MISSING = MISSING
        file_spice: dict | None | MISSING = MISSING

    # Vue 3 from-media payloads omit ``credentials`` and ``fullscreen``;
    # template-derive then inherits the same shape so the
    # ``DesktopFromTemplate`` Pydantic validation has to tolerate the
    # missing keys (otherwise every persistent-from-template create
    # 400s with ``new_from_template: Invalid desktop data``). The
    # defaults match the apiv4 ``DomainGuestProperties`` defaults.
    credentials: _GuestPropertiesCredentials = _GuestPropertiesCredentials()
    fullscreen: bool = False
    viewers: _GuestPropertiesViewers


class DiskTemplate(BaseModel):
    extension: str
    # ``parent`` was historically a path-shaped lineage marker but has no
    # consumers post-MR-3 (engine reads disks[*].file, storage uses
    # storage.parent UUIDs). Made Optional so the validator accepts both
    # old rows that still carry stale path values and new rows written
    # without the field after the writers were dropped — strict-required
    # would break every desktop-from-template create.
    parent: Optional[str] = None
    # ``storage_id`` and ``file`` are populated by apiv4 at desktop-insert
    # time when task-based disk creation pre-allocates the storage, so
    # engine restart cleanup can trace the in-flight task via the
    # ``storage_ids`` multi-index. Declared optional here so Pydantic
    # preserves them through ``model_dump`` — stripping them would open a
    # ~2s window where the domain appears unlinked and
    # ``delete_incomplete_creating_domains`` would clobber it.
    storage_id: Optional[str] = None
    file: Optional[str] = None


class DiskStorage(BaseModel):
    storage_id: str
    bus: Optional[str] = None


class HardwareTemplate(BaseModel):
    """Hardware schema for template creation stage"""

    disks: list[DiskTemplate]
    virtualization_nested: bool = False
    boot_order: Optional[list[Literal["iso", "floppy", "disk", "pxe"]]] = ["disk"]
    qos_disk_id: Optional[str | bool] = False
    vcpus: int
    memory: float
    graphics: list[str] = []
    videos: list[str]
    interfaces: list[str] | list[Interface]
    disk_bus: Literal["default", "ide", "sata", "virtio"] = "default"
    isos: Optional[list[Iso]] = []
    floppies: list[Iso] = []


class HardwareStorage(BaseModel):
    """Hardware schema after storage has been created"""

    disks: list[DiskStorage]
    virtualization_nested: bool = False
    boot_order: Optional[list[Literal["iso", "floppy", "disk", "pxe"]]] = []
    qos_disk_id: Optional[str | bool] = False
    vcpus: int
    memory: int
    graphics: list[str] = []
    videos: list[str]
    interfaces: list[str] | list[Interface]
    disk_bus: Literal["default", "ide", "sata", "virtio"]
    isos: Optional[list[Iso]]
    floppies: list[Iso]
    reservables: Optional[Reservables] = None
