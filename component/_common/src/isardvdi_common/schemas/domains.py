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

import uuid
from enum import Enum
from typing import Optional

from pydantic import UUID4, BaseModel, Field

from .bookings import Reservables
from .shared.allowed import Allowed
from .shared.hardware import (
    GuestProperties,
    Hardware,
    HardwareStorage,
    HardwareTemplate,
)
from .shared.image import Image


class DomainKindEnum(str, Enum):
    desktop = "desktop"
    template = "template"


# Common domain status enums for both desktop and template domains
class DomainStatusEnum(str, Enum):
    creating = "Creating"
    creating_disk = "CreatingDisk"
    starting_paused = "StartingPaused"
    stopped = "Stopped"
    failed = "Failed"
    paused = "Paused"
    unknown = "Unknown"


class DesktopStatusEnum(str, Enum):
    creating = DomainStatusEnum.creating.value
    creating_disk = DomainStatusEnum.creating_disk.value
    creating_and_starting = "CreatingAndStarting"
    # During "create template from desktop" the source domain row
    # is still ``kind=desktop`` while its ``status`` transitions
    # through ``CreatingTemplate`` (see TemplateStatusEnum). API
    # responses that type the row as DesktopStatusEnum (e.g.
    # ``StorageItem.domains[].status`` in
    # ``/api/v4/items/storage/ready``) would otherwise reject the
    # value with a Pydantic enum error.
    creating_template = "CreatingTemplate"
    creating_domain = "CreatingDomain"
    starting = "Starting"
    starting_paused = DomainStatusEnum.starting_paused.value
    starting_domain_disposable = "StartingDomainDisposable"
    started = "Started"
    stopped = DomainStatusEnum.stopped.value
    failed = DomainStatusEnum.failed.value
    shutting_down = "Shutting-down"
    downloading = "Downloading"
    download_starting = "DownloadStarting"
    download_failed = "DownloadFailed"
    creating_disk_from_scratch = "CreatingDiskFromScratch"
    updating = "Updating"
    force_deleting = "ForceDeleting"
    suspended = "Suspended"
    maintenance = "Maintenance"
    stopping = "Stopping"
    paused = DomainStatusEnum.paused.value
    resetting = "Resetting"
    unknown = DomainStatusEnum.unknown.value
    waiting_ip = "WaitingIP"
    deleted = "deleted"
    crashed = "Crashed"


class TemplateStatusEnum(str, Enum):
    creating = DomainStatusEnum.creating.value
    creating_template = "CreatingTemplate"
    creating_domain = "CreatingDomain"
    starting_paused = DomainStatusEnum.starting_paused.value
    stopped = DomainStatusEnum.stopped.value
    failed = DomainStatusEnum.failed.value
    paused = DomainStatusEnum.paused.value
    unknown = DomainStatusEnum.unknown.value


class DomainViewerEnum(str, Enum):
    file_rdpgw = "file_rdpgw"
    browser_rdp = "browser_rdp"
    browser_vnc = "browser_vnc"
    file_rdpvpn = "file_rdpvpn"
    file_spice = "file_spice"


class CreateDictDomain(BaseModel):
    hardware: Hardware
    origin: str
    personal_vlans: bool = False
    reservables: Reservables = {"vgpus": None}


class CreateDictDomainTemplate(BaseModel):
    """CreateDict for template creation stage"""

    hardware: HardwareTemplate
    origin: str
    personal_vlans: bool
    reservables: Reservables = {"vgpus": None}


class CreateDictDomainStorage(BaseModel):
    """CreateDict after storage has been created"""

    hardware: HardwareStorage
    origin: str
    personal_vlans: bool
    reservables: Reservables


class BulkDesktopFromTemplate(BaseModel):
    """Validate each bulk desktop-from-template payload before creation.

    Mirrors the legacy ``desktop_from_template`` cerberus schema: name,
    template and hardware are validated and a fresh ``id`` is generated.
    Bulk-only; single creates validate the built document in
    ``new_from_template``.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=4, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    template_id: str
    hardware: Hardware
    guest_properties: GuestProperties
    image: Image


class DesktopFromTemplate(BaseModel):
    """Used during template creation (before storage)"""

    id: str
    name: str = Field(min_length=4)
    description: str | None = None
    kind: DomainKindEnum
    user: str
    username: str
    status: DesktopStatusEnum
    category: str
    group: str
    icon: str
    image: Image
    os: str
    guest_properties: GuestProperties
    create_dict: CreateDictDomainTemplate
    hypervisors_pools: list[str]
    allowed: Allowed
    accessed: float
    persistent: bool
    forced_hyp: bool | None = None
    favourite_hyp: bool | None = None
    from_template: str
    tag: str | bool | None = None
    tag_visible: bool | None = None
    tag_desktop_id: UUID4 | bool | None = None
    booking_id: str | bool | None = None
    xml: Optional[str] = ""


class DesktopCreated(BaseModel):
    """Used after storage creation"""

    id: str
    name: str = Field(min_length=4)
    description: str | None = None
    kind: DomainKindEnum
    user: str
    username: str
    status: DesktopStatusEnum
    category: str
    group: str
    icon: str
    image: Image
    os: str
    guest_properties: GuestProperties
    create_dict: CreateDictDomainStorage
    hypervisors_pools: list[str]
    allowed: Allowed
    accessed: float
    persistent: bool
    forced_hyp: bool | None = None
    favourite_hyp: bool | None = None
    from_template: str
    tag: str | bool | None = None
    tag_visible: bool | None = None
    booking_id: str | bool | None = None
    xml: Optional[str] = None


class TemplateCreation(BaseModel):
    """Validation gate for ``CommonTemplates.new_template``.

    Mirrors :class:`DesktopFromTemplate` (which is for *desktops*
    being created from a template) with the template-specific
    differences: ``enabled`` and ``tag_name`` are written, ``persistent``
    and ``from_template`` are not (templates are not persistent and
    have no parent template), and ``status`` is ``CreatingTemplate``
    (per :class:`TemplateStatusEnum`).

    The point of running this at insert time is defense-in-depth: the
    ``personal_vlans`` regression on 2026-04-27 silently dropped a
    required ``create_dict`` field for ~16 hours because no schema
    guarded the ``r.table('domains').insert(template_dict)`` call.
    Any future field-drop now fails the insert instead of slipping
    into RethinkDB and surfacing as a 400 on the next
    "create desktop from this template".
    """

    id: str
    name: str = Field(min_length=4)
    description: str | None = None
    kind: DomainKindEnum
    user: str
    username: str
    status: TemplateStatusEnum
    category: str
    group: str
    icon: str
    image: Image
    os: str
    guest_properties: GuestProperties
    create_dict: CreateDictDomainTemplate
    hypervisors_pools: list[str]
    parents: list[str]
    allowed: Allowed
    accessed: float
    enabled: bool
    detail: str | None = None
    tag: str | bool | None = None
    # ``tag_name`` is *required* — making it optional with a default
    # silently masked the apiv4 port forgetting to write it. Defenders
    # inside ``CommonTemplates.new_template`` write ``False`` for
    # non-deployment templates and a string for deployment-tagged
    # templates; both shapes are accepted, ``None`` and missing
    # are not.
    tag_name: str | bool
    tag_visible: bool | None = None
    favourite_hyp: bool | None = None
    forced_hyp: bool | None = None
    xml: Optional[str] = ""


class DomainStatus(BaseModel):
    accessed: float
    status: DomainStatusEnum


class TemplateToDesktop(BaseModel):
    name: str = Field(min_length=4, max_length=50)
    template_id: str
    children: list[str] | None = None
