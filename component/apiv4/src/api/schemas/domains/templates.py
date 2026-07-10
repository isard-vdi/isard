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

from enum import Enum
from typing import Any, Literal, Optional, Union

from api.schemas.common import PaginationResponseList
from api.schemas.domains.hardware import (
    DomainGuestProperties,
    DomainHardware,
    DomainImage,
    Reservables,
)
from isardvdi_common.schemas.domains import DomainViewerEnum, Image, TemplateStatusEnum
from isardvdi_common.schemas.shared.hardware import GuestProperties, Hardware
from pydantic import BaseModel, Field

from ..allowed import Allowed, AllowedBase


class UserTemplateFilterParams(BaseModel):
    enabled: Optional[bool] = Field(
        default=None,
        description="If true, filter enabled templates, if false, filter disabled templates",
    )


class UserTemplateSearchFields(str, Enum):
    name = "name"
    description = "description"


class UserTemplate(BaseModel):
    id: str = Field(
        description="ID of the template",
    )
    name: str = Field(
        description="Name of the template",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the template",
    )
    image: DomainImage | None = Field(
        default=None,
        description="Image of the template. May be None for templates without a custom image assigned.",
    )
    enabled: bool = Field(
        default=True,
        description=(
            "Whether the template is visible to other users. Defaults to "
            "True so legacy template rows (and seeded fixtures) without "
            "the field don't fail Pydantic validation when listed via "
            "``GET /items/templates``. Templates created via the apiv4 "
            "endpoints always set this explicitly. Matches the default "
            "used by the sibling ``enabled`` fields on ``Template`` / "
            "``AdminTemplate`` schemas in this file."
        ),
    )
    status: Optional[TemplateStatusEnum] = Field(
        default=None,
        description=(
            "Domain status of the template row. ``CreatingTemplate`` while "
            "the apiv4 + isard-storage task chain is rewriting the source "
            "desktop's qcow2 into the template; ``Stopped`` once the chain "
            "finishes; ``Failed`` on chain failure."
        ),
    )
    progress: Optional[dict] = Field(
        default=None,
        description=(
            "Progress dict written by the storage worker's ``move()`` task "
            "while the rsync branch of the template-creation chain runs. "
            "Carries ``total_percent`` and ``received_percent`` (both "
            "0-100). Absent for templates not currently being created."
        ),
    )


class UserTemplatesPaginationResponse(PaginationResponseList[UserTemplate]):
    rows: list[UserTemplate] = Field(
        description="List of allowed templates for the current page"
    )


class UserAllowedTemplateSearchFields(str, Enum):
    name = "name"
    description = "description"
    group_name = "group_name"
    category_name = "category_name"


class SharedTemplateUserInfo(BaseModel):
    id: str = Field(
        description="ID of the user that allowed the template",
    )
    name: str = Field(
        description="Name of the user that allowed the template",
    )
    photo: Optional[str] = Field(
        default=None,
        description="Photo of the user that allowed the template",
    )


class UserSharedTemplate(BaseModel):
    id: str = Field(
        description="ID of the allowed template",
    )
    name: str = Field(
        description="Name of the allowed template",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the allowed template",
    )
    image: DomainImage | None = Field(
        default=None,
        description="Image of the allowed template. May be None for templates without a custom image assigned.",
    )
    user: Optional[Union[SharedTemplateUserInfo, str]] = Field(
        default=None,
        description="Owner of the template (user object or user_id string)",
    )
    group_name: Optional[str] = Field(
        default=None,
        description="Name of the group that allowed the template",
    )
    category_name: Optional[str] = Field(
        default=None,
        description="Name of the category of the allowed template",
    )
    status: Optional[TemplateStatusEnum] = Field(
        default=None,
        description=(
            "Domain status of the template row (``CreatingTemplate``, "
            "``Stopped``, or ``Failed``). Surfaced so the frontend can "
            "flag failed shared templates as non-usable."
        ),
    )
    accessed: float = Field(description="Timestamp of the last access to the desktop.")


class UserTemplatesResponse(BaseModel):
    templates: list[UserTemplate] = Field(
        description="List of user templates",
    )


class UserSharedTemplatesResponse(BaseModel):
    templates: list[UserSharedTemplate] = Field(
        description="List of shared templates for the user",
    )


class UserAllowedTemplatesPaginationResponse(
    PaginationResponseList[UserSharedTemplate]
):
    rows: list[UserSharedTemplate] = Field(
        description="List of allowed templates for the current page"
    )


class TemplateResponse(BaseModel):
    id: str
    image: Optional[Image]
    name: str
    description: Optional[str]
    category: Optional[str]
    group: Optional[str]
    user: Optional[str]
    user_name: Optional[str]
    allowed: Optional[Allowed]


class TemplateResponseList(BaseModel):
    templates: list[TemplateResponse]


class TemplateSetEnabledRequest(BaseModel):
    enabled: bool = Field(
        description="Whether the template is enabled (usable for creating desktops).",
    )


class UserAllowedTemplateFlatItem(BaseModel):
    """Single row in the flat allowed-template list returned by
    ``GET /items/templates/allowed/{kind}`` (replaces v3
    ``GET /user/templates/allowed/{kind}``).

    Mirrors the v3 ``allowed.get_items_allowed`` pluck for the template
    kind: ``id``, ``name``, ``kind``, ``category``, ``group``, ``icon``,
    ``image``, ``user``, ``description``, ``status``, ``enabled``, plus
    the merge fields ``category_name`` / ``group_name`` / ``user_name``
    that the helper injects automatically.
    """

    id: str
    name: str
    kind: str = "template"
    category: Optional[str] = None
    category_name: Optional[str] = None
    group: Optional[str] = None
    group_name: Optional[str] = None
    icon: Optional[str] = None
    image: Optional[Any] = None
    user: Optional[Any] = None
    user_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    enabled: Optional[bool] = None
    allowed: Optional[Any] = None

    class Config:
        # Allow any extra column the common helper picks up so a future
        # field addition doesn't break the wire contract.
        extra = "allow"


class TemplateEditRequest(BaseModel):
    name: str = Field(
        description="Name of the template. Must be unique within the user's templates. If not provided, the current value will be kept.",
        min_length=4,
        max_length=50,
        default=None,
    )
    description: str = Field(
        description="Description of the template. If not provided, the current value will be kept.",
        max_length=255,
        default=None,
    )
    guest_properties: DomainGuestProperties = Field(
        description="Guest properties to be set for the template. If not provided, the current value will be kept.",
        default=None,
    )
    hardware: DomainHardware = Field(
        description="Hardware configuration for the template. If not provided, the current value will be kept.",
        default=None,
    )
    reservables: Reservables = Field(
        description="The domain bookable resources. If None, no reservables are available. If not provided, the current value will be kept.",
        default=None,
    )
    image: DomainImage | None = Field(
        default=None,
        description="Image to be used for the template. If None or not provided, the current value will be kept.",
    )
    forced_hyp: list[str] | Literal[False] = Field(
        default=False,
        description=(
            "If set, the desktops will only be able to start on the specified hypervisors."
        ),
    )
    favourite_hyp: list[str] | Literal[False] = Field(
        default=False,
        description=(
            "If set, the desktops will start on the specified hypervisors if available, but can start on other hypervisors if the favourite ones are not available."
        ),
    )


class TemplateToDesktopRequest(BaseModel):
    name: str | None = Field(
        description="Name of the desktop. Must be unique within the user's desktops. If not provided, the template name will be used.",
        min_length=4,
        max_length=50,
        default=None,
    )


class NewTemplateRequest(BaseModel):
    desktop_id: str = Field(
        description="ID of the desktop to template.",
    )
    name: str = Field(
        description="Name of the template. Must be unique within the user's templates.",
        min_length=4,
        max_length=50,
    )
    description: str = Field(
        description="Description of the template.",
        max_length=255,
    )
    allowed: Allowed = Field(
        description="Permissions for the template.",
    )
    enabled: bool = Field(
        description="Whether the template is enabled or not.",
        default=True,
    )


class DuplicateTemplateRequest(BaseModel):
    name: str = Field(
        description="Name of the template. Must be unique within the user's templates.",
        min_length=4,
        max_length=50,
    )
    description: str = Field(
        description="Description of the template.",
        max_length=255,
    )
    allowed: AllowedBase = Field(
        description="Permissions for the template.",
    )
    enabled: bool = Field(
        description="Whether the template is enabled or not.",
        default=True,
    )


class TemplateTreeDomains(BaseModel):
    id: str = Field(
        description="ID of the domain (desktop or template).",
    )
    kind: str = Field(
        description="Kind of the domain (desktop or template).",
    )
    name: str = Field(
        description="Name of the domain.",
    )
    user: str = Field(
        description="ID of the user that owns the domain.",
    )


class TemplateTreeResponse(BaseModel):
    domains: list[TemplateTreeDomains | dict] = Field(
        description="List of desktops and templates that depend on this template.",
    )
    deployments: list[TemplateTreeDomains | dict] = Field(
        default_factory=list,
        description="List of deployments that depend on this template.",
    )
    pending: bool = Field(
        description="Whether the template has pending desktops or templates.",
    )
    is_duplicated: bool = Field(
        description="Whether the template is a duplicate of another template.",
    )
    cross_category: bool = Field(
        default=False,
        description="Whether the template has derivatives in other categories.",
    )


class TemplateNamedResource(BaseModel):
    id: str = Field(
        description="ID of the resource, such as a disk, video, or ISO.",
    )
    name: str = Field(
        description="Name of the resource, such as a disk, video, or ISO.",
    )


class TemplateStorage(BaseModel):
    id: str = Field(
        description="ID of the storage where the disk is located.",
    )
    size: float = Field(
        description="Size of the storage in GB.",
    )


class TemplateDetailsResponse(BaseModel):
    name: str = Field(
        description="Name of the template.",
    )
    description: str = Field(
        default=None,
        description="Description of the template.",
    )
    image: DomainImage = Field(
        description="Image associated with the template.",
    )
    vcpu: float = Field(
        default=0,
        description="Number of virtual CPUs allocated to the template.",
    )
    memory: float = Field(
        default=0,
        description="Amount of memory (RAM) allocated to the template in GB.",
    )
    boot_order: list[TemplateNamedResource] = Field(
        description="List of IDs and names with the boot order that will be followed when booting the template. Each ID will be a valid boot id.",
    )
    disk_bus: str = Field(
        description="Type of disk bus used by the desktop, e.g., 'virtio', 'scsi'.",
    )
    interfaces: list[TemplateNamedResource] = Field(
        description="List of IDs and names with the network interfaces that will be attached to the template. Each ID will be a valid network interface id.",
    )
    disks: list[TemplateStorage] = Field(
        description="List of disks that will be attached to the template. Each disk will have a storage_id and its size.",
    )
    videos: list[TemplateNamedResource] = Field(
        description="List of IDs and names with the videos order that will be followed. Each ID will be a valid video id.",
    )
    viewers: list[DomainViewerEnum] = Field(
        default=[],
        description="List of viewers that will be available to access the template.",
    )
    fullscreen: bool = Field(
        default=False,
        description="If true, the template will be opened in fullscreen mode by default.",
    )
    isos: list[TemplateNamedResource] | None = Field(
        default=None,
        description="List of ISO images that will be attached to the template. Each ISO will have an ID and a name.",
    )
    reservables: Reservables = Field(
        default={"vgpus": None}, description="The template bookable resources."
    )
    credentials: DomainGuestProperties._GuestPropertiesCredentials = Field(
        description="Credentials that will be set in the guest OS of the template.",
    )
