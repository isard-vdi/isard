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

from typing import Literal, Optional, Union

from isardvdi_common.schemas.domains import DomainViewerEnum
from pydantic import BaseModel, Field, field_validator


class DomainImageFile(BaseModel):
    data: str = Field(
        description=(
            "Base64-encoded image data (without the 'data:<mime>;base64,' " "prefix)."
        ),
    )
    filename: str = Field(
        description="Original filename of the uploaded image.",
    )


class DomainImage(BaseModel):
    id: str = Field(
        description="ID of the image to be used for the domain.",
    )
    type: str = Field(
        description="Type of the image. This string can be either 'stock' or 'user'.",
    )
    url: Optional[str] = Field(
        default=None,
        description="URL of the image.",
    )
    file: Optional[DomainImageFile] = Field(
        default=None,
        exclude=True,
        description=(
            "Optional file payload used to upload a new user card on desktop "
            "edit. When set, the backend saves the image and replaces the "
            "desktop's card with it (see `isardvdi_common.helpers.cards.Cards.upload`). "
            "Excluded from JSON serialization (write-only)."
        ),
    )


class Reservables(BaseModel):
    vgpus: list[str] | None = Field(
        default=None,
        description="List of IDs of vGPUs that can be reserved for the desktop. If None, no vGPUs can be reserved nor used. Each ID must be a valid vGPU ID.",
    )

    @field_validator("vgpus", mode="before")
    def remove_none(cls, v):
        if v is not None:
            if "None" in v:
                v.remove("None")

            if len(v) == 0:
                return None

        return v


class DomainHardwareResource(BaseModel):
    id: str = Field(
        description="ID of the hardware resource.",
    )
    name: str = Field(
        description="Name of the hardware resource.",
    )


class DomainHardware(BaseModel):
    memory: Optional[float] = Field(
        default=1,
        ge=0.025,
        description="Amount of memory (RAM) allocated to the domain in GB (GiB). Minimum: 0.025 GB.",
    )
    vcpus: Optional[int] = Field(
        default=1,
        ge=1,
        description="Number of virtual CPUs allocated to the domain. Minimum: 1 vCPU.",
    )
    boot_order: Optional[list[Literal["iso", "floppy", "disk", "pxe"]]] = Field(
        default=["disk"],
        description="List of boot devices in the order they will be used to boot the domain. Each device must be one of 'iso', 'floppy', 'disk', or 'pxe'.",
    )
    disk_bus: Optional[str] = Field(
        default="Default",
        description="The ID of the disk bus that will be used for the domain disks. The disk bus must be a valid disk bus id.",
    )
    floppies: Optional[list[DomainHardwareResource]] = Field(
        default=None,
        description="List of floppy disk images to be attached to the domain. Each floppy must be provided as an object with id and name.",
    )
    interfaces: Optional[list[str]] = Field(
        default=None,
        description="List of network interfaces to be used by the domain. Each interface can be a string ID or an Interface object.",
    )
    isos: Optional[list[DomainHardwareResource]] = Field(
        default=None,
        description="List of ISO images to be attached to the domain. Each ISO must be provided as an object with id and name.",
    )
    videos: Optional[list[str]] = Field(
        default=["default"],
        description="List of video devices to be used by the domain. Each device must be a valid video device ID.",
    )


class DomainGuestProperties(BaseModel):

    class _GuestPropertiesCredentials(BaseModel):
        username: Optional[str] = Field(
            default="isard",
            description="Username for accessing the desktop using RDP.",
        )
        password: Optional[str] = Field(
            default="pirineus",
            description="Password for accessing the desktop using RDP.",
        )

    class _ViewerConfig(BaseModel):
        options: dict | None = Field(
            default=None,
            description="Configuration options for the viewer. Can be null if no specific options are set.",
        )

    class _GuestPropertiesViewers(BaseModel):
        browser_rdp: Optional["DomainGuestProperties._ViewerConfig"] = Field(
            default=None,
            description="Configuration for browser-based RDP access.",
        )
        browser_vnc: Optional["DomainGuestProperties._ViewerConfig"] = Field(
            default=None,
            description="Configuration for browser-based VNC access.",
        )
        file_rdpgw: Optional["DomainGuestProperties._ViewerConfig"] = Field(
            default=None,
            description="Configuration for file-based RDP gateway access.",
        )
        file_rdpvpn: Optional["DomainGuestProperties._ViewerConfig"] = Field(
            default=None,
            description="Configuration for file-based RDP VPN access.",
        )
        file_spice: Optional["DomainGuestProperties._ViewerConfig"] = Field(
            default=None,
            description="Configuration for file-based SPICE access.",
        )

    credentials: Optional[_GuestPropertiesCredentials] = Field(
        default=None,
        description="Credentials for accessing the desktop using RDP. If not provided, the desktop will not be accessible.",
    )
    fullscreen: bool = Field(
        default=False,
        description="If true, the desktop will be opened in fullscreen mode by default.",
    )
    viewers: Optional[_GuestPropertiesViewers] = Field(
        default=None,
        description="Configuration for various viewers that will be available to access the desktop. Only the configured viewers will be available.",
    )


class MediaHardware(BaseModel):
    boot_order: list[str]
    disk_bus: str
    disk_size: int = Field(
        ge=1,
        description="Size of the disk to create/attach in GB (GiB). Minimum: 1 GB.",
    )
    interfaces: list[str]
    memory: float = Field(
        ge=0.025,
        description="Amount of memory (RAM) allocated in GB (GiB). Minimum: 0.025 GB.",
    )
    vcpus: int = Field(
        ge=1,
        description="Number of virtual CPUs allocated. Minimum: 1 vCPU.",
    )
    videos: list[str]
    reservables: Optional[Reservables] = None


class Disk(BaseModel):
    storage_id: str = Field(description="The ID of a storage.")
