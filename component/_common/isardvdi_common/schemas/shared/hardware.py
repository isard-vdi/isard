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

from typing import Literal, Optional

from pydantic import BaseModel
from pydantic.experimental.missing_sentinel import MISSING

from ..bookings import Reservables


class Disk(BaseModel):
    storage_id: Optional[str] = None
    bus: Optional[str] = False
    extension: Optional[str] = None
    parent: Optional[str] = None


class Iso(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None


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
        username: str
        password: str

    class _GuestPropertiesViewers(BaseModel):
        browser_rdp: dict | MISSING = MISSING
        browser_vnc: dict | MISSING = MISSING
        file_rdpgw: dict | MISSING = MISSING
        file_rdpvpn: dict | MISSING = MISSING
        file_spice: dict | MISSING = MISSING

    credentials: _GuestPropertiesCredentials
    fullscreen: bool
    viewers: _GuestPropertiesViewers


class DiskTemplate(BaseModel):
    extension: str
    parent: str
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
