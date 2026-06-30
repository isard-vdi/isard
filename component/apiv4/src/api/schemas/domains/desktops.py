#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar, Miriam Melina Gamboa Valdez
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

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional, Union

from api.schemas.common import PaginationResponseList
from isardvdi_common.schemas.domains import DesktopStatusEnum, DomainViewerEnum
from isardvdi_common.schemas.media import MediaKindEnum
from isardvdi_common.schemas.shared.hardware import GuestProperties, Hardware
from pydantic import BaseModel, ConfigDict, Field

from ..allowed import Allowed, AllowedBase
from ..bastion import BastionHttpConfig, BastionRequest, BastionSshConfig
from .hardware import (
    DomainGuestProperties,
    DomainHardware,
    DomainImage,
    MediaHardware,
    Reservables,
)


class CreateDesktopRequest(BaseModel):
    # TODO: Consider allowing non-persistent desktops to be created with the fields description, guest_properties, hardware, and image.
    template_id: str = Field(
        description="ID of the template to use for creating the desktop."
    )
    name: str = Field(
        description="Name of the desktop to be created. Must be unique within the user desktops.",
        min_length=4,
        max_length=50,
    )
    description: str | None = Field(
        default=None,
        description="Description of the desktop to be created. When creating a temporal desktop this field will be ignored.",
        min_length=0,
        max_length=255,
    )
    persistent: bool = Field(
        default=True,
        description="If true, the desktop will be persistent and will not be deleted after shutdown. Otherwise, it will be non-persistent and will be deleted after shutdown.",
    )
    guest_properties: Optional[DomainGuestProperties] = Field(
        default=None,
        description="Guest properties to be set for the desktop. If not provided, the template guest properties will be inherited. When creating a temporal desktop this field will be ignored and the template guest properties will be inherited.",
    )
    hardware: Optional[DomainHardware] = Field(
        default=None,
        description="Hardware configuration for the desktop. If not provided, the template hardware will be inherited. When creating a temporal desktop this field will be ignored and the template hardware will be inherited.",
    )
    reservables: Optional[Reservables] = Field(
        default=None,
        description="The domain bookable resources. If None, no reservables are available.",
    )
    image: Optional[DomainImage] = Field(
        default=None,
        description="Image to be used for the desktop. If not provided, the template image will be inherited. When creating a temporal desktop this field will be ignored and the image will be inherited.",
    )
    bastion_target: BastionRequest | None = Field(
        default=None,
        description="Bastion configuration for the desktop. If not provided, the bastion configuration will not be modified.",
    )


class DesktopsStopRequest(BaseModel):
    force: Optional[bool] = Field(
        default=False,
        description="If true, the desktop will be stopped forcefully. If false, the desktop will be stopped gracefully.",
    )


class DesktopNetwork(BaseModel):
    id: str = Field(
        description="ID of the network interface.",
    )
    name: str = Field(
        description="Name of the network interface.",
    )
    mac: str = Field(
        description="MAC address of the network interface.",
    )


class DesktopNetworksResponse(BaseModel):
    networks: list[DesktopNetwork] = Field(
        default=[],
        description="List of networks available for the desktop.",
    )


class DesktopNamedResource(BaseModel):
    id: str = Field(
        description="ID of the resource, such as a disk, video, or ISO.",
    )
    name: str = Field(
        description="Name of the resource, such as a disk, video, or ISO.",
    )


class DesktopStorage(BaseModel):
    id: str = Field(
        description="ID of the storage where the disk is located.",
    )
    size: float = Field(
        description="Size of the storage in GB.",
    )


class DesktopTemplate(BaseModel):
    id: str = Field(
        description="ID of the template.",
    )
    name: str = Field(
        description="Name of the template.",
    )


class DesktopDetailsResponse(BaseModel):
    id: str = Field(
        description="ID of the desktop.",
    )
    name: str = Field(
        description="Name of the desktop.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the desktop.",
    )
    ip: Optional[str] = Field(
        default=None,
        description="IP address of the desktop.",
    )
    vcpu: float = Field(
        default=0,
        description="Number of virtual CPUs allocated to the desktop.",
    )
    memory: float = Field(
        default=0,
        description="Amount of memory (RAM) allocated to the desktop in GiB.",
    )
    disk_bus: str = Field(
        description="Type of disk bus used by the desktop, e.g., 'virtio', 'scsi'.",
    )
    boot_order: list[DesktopNamedResource] = Field(
        description="List of IDs and names with the boot order that will be followed when booting the domain. Each ID will be a valid boot id.",
    )
    disks: list[DesktopStorage] = Field(
        description="List of disks that will be attached to the domain. Each disk will have a storage_id and its size.",
    )
    videos: list[DesktopNamedResource] = Field(
        description="List of IDs and names with the videos order that will be followed. Each ID will be a valid video id.",
    )
    viewers: list[DomainViewerEnum] = Field(
        default=[],
        description="List of viewers that will be available to access the desktop.",
    )
    fullscreen: bool = Field(
        default=False,
        description="If true, the desktop will be opened in fullscreen mode by default.",
    )
    isos: list[DesktopNamedResource] | None = Field(
        default=None,
        description="List of ISO images that will be attached to the desktop. Each ISO will have an ID and a name.",
    )
    floppies: list[DesktopNamedResource] | None = Field(
        default=None,
        description="List of floppy images that will be attached to the desktop. Each floppy will have an ID and a name.",
    )
    reservables: Reservables = Field(
        default={"vgpus": None}, description="The domain bookable resources."
    )
    status: DesktopStatusEnum = Field(
        description="Status of the desktop.",
    )
    interfaces: list[DesktopNetwork] = Field(
        description="List of network interfaces attached to the desktop. Each interface will have an ID, a name, and a MAC address.",
    )
    credentials: Optional[DomainGuestProperties._GuestPropertiesCredentials] = Field(
        default=None,
        description="Credentials to access the desktop, if available. The keys of the dictionary will be the types of credentials, such as 'rdp', 'vnc', 'ssh', and the values will be the corresponding credentials, such as the password or the private key.",
    )
    template: Optional[DesktopTemplate] = Field(
        default=None,
        description="Template used to create the desktop, if available.",
    )


class BastionAuthorizedKeysUpdateRequest(BaseModel):
    authorized_keys: list[str] = Field(
        default=[],
        description="List of SSH public keys to be authorized for the bastion SSH access. If empty, the authorized keys will be cleared.",
    )


class BastionDomainUpdateRequest(BaseModel):
    domain_name: str | None = Field(
        description="The domain name to be set for the bastion target of the desktop.",
    )


class NewNonpersistentDesktopRequest(BaseModel):
    """Minimal request body for the v3-parity non-persistent desktop
    endpoint (``POST /item/desktop/new-nonpersistent``).

    v3 accepted a form-encoded body with just a ``template`` field
    and generated the rest server-side. This schema mirrors that
    shape as JSON.
    """

    template_id: str = Field(
        description="ID of the template to create a non-persistent desktop from.",
    )


class BastionDomainsUpdateRequest(BaseModel):
    """Bulk update of the bastion ``domains`` list (up to 10)."""

    domains: list[str] = Field(
        default=[],
        max_length=10,
        description=(
            "Up to 10 bastion domain names to set for the desktop. An "
            "empty list clears the domains."
        ),
    )


class BastionDomainVerifyRequest(BaseModel):
    """Ad-hoc DNS verification of a single bastion domain without
    saving it."""

    domain: str = Field(
        min_length=1,
        description="The candidate bastion domain to DNS-verify.",
    )


class BastionDomainVerifyResponse(BaseModel):
    verified: bool = Field(
        description="True if the DNS record for ``domain`` resolves to "
        "the desktop's expected CNAME target.",
    )


class DesktopBastionResponse(BaseModel):
    id: str = Field(
        description="ID of the bastion configuration for the desktop.",
    )
    user_id: str = Field(
        description="ID of the user who owns the desktop.",
    )
    desktop_id: str = Field(
        description="ID of the desktop associated with the bastion configuration.",
    )
    domain: Optional[str] = Field(
        default=None,
        description="Domain associated with the bastion configuration. If None, the bastion is not associated with any domain.",
    )
    http: BastionHttpConfig = Field(
        description="HTTP configuration for the bastion.",
    )
    ssh: BastionSshConfig = Field(
        description="SSH configuration for the bastion.",
    )


class DesktopImageType(str, Enum):
    stock = "stock"
    # user = "user" # TODO: user cards are not implemented yet, so we return stock cards only


# Mock schemas
# TODO: remove these when the real schemas are implemented


class UserDesktopBastionTarget(BaseModel):
    http: BastionHttpConfig
    id: str
    ssh: BastionSshConfig
    domain: str | None = None


class Desktop(BaseModel):
    image: DomainImage | None = Field(
        default=None,
        description="Image of the desktop. May be None for desktops without a custom image assigned.",
    )
    name: str = Field(
        description="Name of the desktop.",
    )
    id: str = Field(
        description="ID of the desktop.",
    )
    status: DesktopStatusEnum = Field(
        description="Status of the desktop.",
    )
    ip: Optional[str] = Field(
        default=None,
        description="IP address of the desktop. If None, the desktop is not running or does not have an IP assigned.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the desktop.",
    )
    tag_visible: bool = Field(
        default=False, description="If true, the desktop will be visible."
    )
    accessed: float = Field(description="Timestamp of the last access to the desktop.")
    user: str = Field(description="ID of the user who owns the desktop.")


class UserDesktopInterface(BaseModel):
    id: str
    mac: str


class UserDesktopScheduled(BaseModel):
    shutdown: Union[datetime, Literal[False], None] = Field(
        default=None,
        description="Scheduled shutdown time for the desktop. If False, no shutdown is scheduled. If None, the desktop is not scheduled.",
    )


class UserDesktopProgress(BaseModel):
    percentage: int = Field(default=0, description="Progress percentage")
    throughput_average: str = Field(default="0", description="Average throughput")
    time_left: str = Field(default="00:00:00", description="Estimated time remaining")
    size: str = Field(default="0k", description="Size of the operation")


class UserDesktop(BaseModel):
    id: str = Field(
        description="ID of the desktop.",
    )
    name: str = Field(
        description="Name of the desktop.",
    )
    status: DesktopStatusEnum = Field(
        description="Status of the desktop.",
    )
    type: str = Field(
        description="Type of the desktop, e.g., 'persistent', 'non-persistent'.",
    )
    template: Optional[str] = Field(
        default=None,
        description="ID of the template used to create the desktop. If None, the desktop is not based on a template (mainly desktops created through media).",
    )
    viewers: list[str] = Field(
        description="List of available viewers for the desktop.",
    )
    icon: Optional[str] = Field(
        default=None,
        description="Icon of the desktop, if available. If None, no icon is set.",
    )
    image: Optional[DomainImage] = Field(
        default=None,
        description="Image of the desktop. If None, no image is set.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the desktop.",
    )
    ip: Optional[str] = Field(
        default=None,
        description="IP address of the desktop. If None, the desktop is not running or does not have an IP assigned.",
    )
    progress: Optional[UserDesktopProgress] = Field(
        default=None,
        description="Progress of the desktop, if applicable. Can be a string or an integer.",
    )
    editable: bool | None = Field(
        default=False,
        description="If true, the desktop can be edited. If false, the desktop cannot be edited.",
    )
    scheduled: Optional[UserDesktopScheduled] = Field(
        default=None,
        description="Scheduled actions for the desktop, such as shutdown. If None, no scheduled actions are set.",
    )
    server: bool | None = Field(
        default=None,
        description="If true, the desktop is a server. If false, the desktop is not a server.",
    )
    accessed: Optional[int] = Field(
        default=None,
        description="Timestamp of the last access to the desktop. If None, the desktop has not been accessed yet.",
    )
    tag: Optional[Union[str, bool]] = Field(
        default=False,
        description="Tag associated with the desktop. If False, no tag is set. If a string, it represents the tag ID.",
    )
    visible: Optional[bool] = Field(
        default=False,
        description="If true, the desktop is visible to the user. If false, the desktop is not visible.",
    )
    user: str = Field(
        description="ID of the user who owns the desktop.",
    )
    group: str = Field(description="ID of the group that owns the desktop.")
    category: str = Field(description="ID of the category that owns the desktop.")
    reservables: Reservables = Field(
        default={"vgpus": None},
        description="The domain bookable resources associated with the desktop.",
    )
    interfaces: List[UserDesktopInterface] = Field(
        description="List of network interfaces associated with the desktop.",
    )
    current_action: Optional[str] = Field(
        default=None,
        description="Current action being performed on the desktop, if any. If None, no action is being performed.",
    )
    storage: Optional[List[str]] | List[None] = Field(
        description="List of storage IDs associated with the desktop.",
    )
    permissions: List[str] = Field(
        default=[],
        description="List of permissions the user has on the desktop, such as 'recreate'",
    )
    needs_booking: bool = Field(
        default=False,
        description="If true, the desktop needs to be booked before use. If false, no booking is required.",
    )
    next_booking_start: Optional[datetime] = Field(
        default=None,
        description="Start time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    next_booking_end: Optional[datetime] = Field(
        default=None,
        description="End time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    booking_id: Union[str, bool, None] = Field(
        default=None,
        description="ID of the booking associated with the desktop. If False, no booking is required. If None, the desktop is not booked.",
    )
    bastion_target: UserDesktopBastionTarget | None = Field(
        default=None,
        description="Bastion target configuration for the desktop. If None, no bastion is configured. If a dict, it contains the bastion configuration.",
    )


class UserDesktopsResponse(BaseModel):
    desktops: List[UserDesktop] = Field(
        description="List of user desktops.",
    )


class DesktopFilterParams(BaseModel):
    tag: Optional[bool] = Field(
        default=None,
        description="If true, filter desktops by tag. If false, do not filter by tag.",
    )
    persistent: Optional[bool] = Field(
        default=None,
        description="If true, filter desktops by persistence. If false, do not filter by persistence.",
    )


class DesktopSearchFields(str, Enum):
    name = "name"
    description = "description"
    group_name = "group_name"


# Specific pagination response for desktops
class DesktopsPaginationResponse(PaginationResponseList[UserDesktop]):
    rows: list[UserDesktop] = Field(
        description="List of desktop items for the current page"
    )


class CreateDesktopFromMedia(BaseModel):
    media_id: str
    kind: MediaKindEnum
    os_template: str  # hardware template ID
    name: str = Field(
        description="Name of the desktop to be created. Must be unique within the user desktops.",
        min_length=4,
        max_length=50,
    )
    description: str = Field(
        default="",
        description="Description of the desktop to be created.",
        max_length=255,
    )
    guest_properties: DomainGuestProperties
    hardware: MediaHardware
    image: Optional[DomainImage] = Field(
        default=None,
        description="Image to be used for the desktop. If not provided, a default stock card will be assigned.",
    )


class BulkEditDesktopsRequest(BaseModel):
    """Request body for ``PUT /items/desktops/bulk-edit``.

    The route applies a partial update to every desktop in ``ids``; the
    remaining fields are forwarded to ``CommonDesktops.update_desktop``
    in bulk mode.
    """

    ids: list[str] = Field(
        description="List of desktop IDs to update.",
        min_length=1,
    )
    name: Optional[str] = Field(default=None, description="New desktop name")
    description: Optional[str] = Field(
        default=None, description="New desktop description"
    )
    guest_properties: Optional[DomainGuestProperties] = Field(
        default=None,
        description="Updated guest properties (credentials, viewers, fullscreen)",
    )
    # DomainHardware (not the strict shared ``Hardware``) so the bulk
    # form can send only the fields the operator actually changed —
    # ``videos`` and ``interfaces`` are commonly omitted.
    hardware: Optional[DomainHardware] = Field(
        default=None, description="Updated hardware spec"
    )
    reservables: Optional[Reservables] = Field(
        default=None,
        description="Updated bookable resources (vGPUs).",
    )

    class Config:
        # Allow callers to send any subset of update fields the
        # webapp's bulk-edit form supports today (image, reservables,
        # bastion_target, ...) without forcing a schema migration for
        # every minor edit field.
        extra = "allow"


class BulkCreatePersistentDesktopsRequest(BaseModel):
    """Request body for ``POST /items/desktops/bulk-create``.

    Creates many persistent desktops from a single template for a set
    of users / groups / categories / roles. The actual fan-out happens
    inside ``CommonDesktops.bulk_create_desktops``.
    """

    template_id: str = Field(description="ID of the template to clone from.")
    name: str = Field(
        description="Base name for the created desktops.",
        min_length=4,
        max_length=50,
    )
    description: str = Field(default="", description="Description.", max_length=255)
    allowed: Allowed = Field(
        description=(
            "Set of users / groups / categories / roles to fan out to. "
            "Each member receives one desktop."
        ),
    )


class AllowedReservableItem(BaseModel):
    allowed: Allowed
    description: str
    id: str
    name: str
    editable: bool


class AllowedReservablesResponse(BaseModel):
    vgpus: list[AllowedReservableItem]


class DomainInfoBastionResponse(BaseModel):
    id: str = Field(
        description="ID of the bastion configuration for the desktop.",
    )
    domain: str | None = Field(
        default=None,
        description="Domain associated with the bastion configuration. If None, the bastion is not associated with any domain.",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Custom CNAMEs configured on this bastion target.",
    )
    http: BastionHttpConfig = Field(
        description="HTTP configuration for the bastion.",
    )
    ssh: BastionSshConfig = Field(
        description="SSH configuration for the bastion.",
    )
    bastion_domain: str | None = Field(
        default=None,
        description="Global bastion domain. Used by the admin info modal to compose the per-target subdomain.",
    )
    ssh_port: str | None = Field(
        default=None,
        description="Global bastion SSH port. None when bastion is disabled.",
    )


class DomainOwnerResponse(BaseModel):
    id: str = Field(description="Owner user ID.")
    username: str | None = None
    name: str | None = None
    email: str | None = None
    role_id: str | None = Field(default=None, alias="role")
    category_id: str | None = Field(default=None, alias="category")
    category_name: str | None = None
    group_id: str | None = Field(default=None, alias="group")
    group_name: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class DomainInterfaceResponse(BaseModel):
    id: str
    name: str | None = None
    mac: str | None = None


class DomainInfoMedia(BaseModel):
    id: str
    name: Optional[str] = None


class DomainInfoHardware(Hardware):
    isos: Optional[list[DomainInfoMedia]] = []
    floppies: Optional[list[DomainInfoMedia]] = []


class DomainInfoResponse(BaseModel):
    id: str
    kind: str
    name: str
    description: str = ""
    image: DomainImage | None = None
    guest_properties: DomainGuestProperties | None = None
    hardware: DomainInfoHardware | None = None
    reservables: Reservables | None = None
    limited_hardware: dict | None = None  # TODO: check type
    bastion_target: DomainInfoBastionResponse | None = None
    status: str | None = None
    hyp_started: str | None = None
    guest_ip: str | None = None
    deployment_name: str | None = None
    storage_id: str | None = None
    owner: DomainOwnerResponse | None = None
    interfaces: list[DomainInterfaceResponse] | None = None


class DesktopImagesResponse(BaseModel):
    images: list[DomainImage]


# TODO: For now pagination won't be used since the user load is not as high. Although this works, it is not needed yet.


class DesktopFilterParams(BaseModel):
    tag: Optional[bool] = Field(
        default=None,
        description="If true, filter desktops by tag. If false, do not filter by tag.",
    )
    persistent: Optional[bool] = Field(
        default=None,
        description="If true, filter desktops by persistence. If false, do not filter by persistence.",
    )


class DesktopSearchFields(str, Enum):
    name = "name"
    description = "description"
    group_name = "group_name"


# Specific pagination response for desktops
class DesktopPaginationResponse(PaginationResponseList[UserDesktop]):
    rows: list[UserDesktop] = Field(
        description="List of desktop items for the current page"
    )


class DesktopEditRequest(BaseModel):
    name: str = Field(
        description="Name of the desktop to be created. Must be unique within the user desktops. If not provided, the current value will be kept.",
        min_length=4,
        max_length=50,
        default=None,
    )
    description: str = Field(
        description="Description of the desktop to be created. If not provided, the current value will be kept.",
        max_length=255,
        default=None,
    )
    guest_properties: DomainGuestProperties = Field(
        description="Guest properties to be set for the desktop. If not provided, the current value will be kept.",
        default=None,
    )
    hardware: DomainHardware = Field(
        description="Hardware configuration for the desktop. If not provided, the current value will be kept.",
        default=None,
    )
    reservables: Reservables = Field(
        description="The domain bookable resources. If None, no reservables are available. If not provided, the current value will be kept.",
        default=None,
    )
    image: DomainImage | None = Field(
        default=None,
        description="Image to be used for the desktop. If None or not provided, the current value will be kept.",
    )
    bastion_target: BastionRequest = Field(
        description="Bastion configuration for the desktop. If not provided, the bastion configuration will not be modified.",
        default=None,
    )
    forced_hyp: list[str] | Literal[False] = Field(
        description="List of hypervisor IDs to force the desktop onto, or False to clear it. Requires manager or admin role. If not provided, the current value will be kept.",
        default=None,
    )
    favourite_hyp: list[str] | Literal[False] = Field(
        description="List of preferred hypervisor IDs, or False to clear it. Requires manager or admin role. If not provided, the current value will be kept.",
        default=None,
    )
    server: bool = Field(
        description="If true, mark the desktop as a server. Requires manager or admin role. If not provided, the current value will be kept.",
        default=None,
    )
    server_autostart: bool = Field(
        description="If true, the server desktop is autostarted. Requires manager or admin role and server=True. If not provided, the current value will be kept.",
        default=None,
    )


class DesktopGetViewerResponse(BaseModel):
    """Response model for desktop viewer connection string"""

    kind: Literal["browser", "file"] = Field(
        ..., description="Type of viewer - 'browser' or 'file'"
    )
    protocol: Literal["rdp", "vnc", "rdpvpn", "rdpgw", "spice"] = Field(
        ..., description="Protocol used for the connection"
    )

    # Browser viewer fields (when kind="browser")
    viewer: Optional[str] = Field(None, description="URL to the browser viewer")
    urlp: Optional[str] = Field(None, description="URL with parameters for the viewer")
    cookie: Optional[str] = Field(None, description="JWT token for authentication")
    values: Optional[dict[str, Union[str, int, float, bool]]] = Field(
        None, description="Decoded values from the cookie"
    )

    # File viewer fields (when kind="file")
    name: Optional[str] = Field(None, description="Name of the file to be downloaded")
    ext: Optional[str] = Field(None, description="File extension")
    mime: Optional[str] = Field(None, description="MIME type of the file")
    content: Optional[str] = Field(None, description="File content")
