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


from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from isardvdi_common.schemas.domains import DesktopStatusEnum
from pydantic import BaseModel, Field


class DesktopUpdateShareLinkRequest(BaseModel):
    enabled: bool = Field(
        default=True,
        description="If false, the share link will be disabled. If true, the share link will be enabled or regenerated.",
    )


class DesktopViewerScheduled(BaseModel):
    shutdown: Union[datetime, Literal[False], None] = Field(
        default=False,
        description="Scheduled shutdown time for the desktop. If False, no shutdown is scheduled. If None, the desktop is not scheduled.",
    )


class ViewerKind(str, Enum):
    FILE = "file"
    BROWSER = "browser"


class ViewerProtocol(str, Enum):
    SPICE = "spice"
    VNC = "vnc"
    RDP = "rdp"
    RDPGW = "rdpgw"
    RDPVPN = "rdpvpn"


class ScheduledModel(BaseModel):
    shutdown: bool


class BrowserVNCValues(BaseModel):
    vmName: str
    vmHost: str
    vmPort: str
    host: str
    port: str
    token: str
    exp: float


class FileSpiceViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    name: str
    ext: str
    mime: str
    content: str


class BrowserVNCViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    viewer: str
    urlp: str
    cookie: str
    values: BrowserVNCValues


class BrowserRDPValues(BaseModel):
    vmName: str
    vmHost: str
    vmUsername: str
    vmPassword: str
    host: str
    port: str
    exp: float


class BrowserRDPViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    viewer: str
    urlp: str
    cookie: str
    values: BrowserRDPValues


class FileRDPGWViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    name: str
    ext: str
    mime: str
    content: str


class FileRDPVPNViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    name: str
    ext: str
    mime: str
    content: str


class ViewersModel(BaseModel):
    file_spice: Optional[FileSpiceViewer] = Field(None, alias="file-spice")
    browser_vnc: Optional[BrowserVNCViewer] = Field(None, alias="browser-vnc")
    browser_rdp: Optional[BrowserRDPViewer] = Field(None, alias="browser-rdp")
    file_rdpgw: Optional[FileRDPGWViewer] = Field(None, alias="file-rdpgw")
    file_rdpvpn: Optional[FileRDPVPNViewer] = Field(None, alias="file-rdpvpn")

    model_config = {"populate_by_name": True}


class DesktopViewerResponse(BaseModel):
    id: str = Field(
        description="ID of the desktop.",
    )
    jwt: str = Field(
        description="JWT token to access the desktop.",
    )
    name: str = Field(
        description="Name of the desktop.",
    )
    description: str = Field(
        default=None,
        description="Description of the desktop.",
    )
    status: DesktopStatusEnum = Field(
        description="Status of the desktop.",
    )
    scheduled: DesktopViewerScheduled = Field(
        description="Scheduled actions for the desktop viewer.",
    )
    viewers: ViewersModel = Field(
        description="List of available viewers for the desktop.",
    )
    needs_booking: Optional[bool] = Field(
        default=False,
        description="If true, the desktop needs to be booked.",
    )
    next_booking_start: Optional[str] = Field(
        default=None,
        description="Start time of the next booking.",
    )
    next_booking_end: Optional[str] = Field(
        default=None,
        description="End time of the next booking.",
    )


class ViewersDocsResponse(BaseModel):
    viewers_documentation_url: str = Field(
        description="URL to the documentation of the possible viewers.",
    )


class DesktopShareLinkResponse(BaseModel):
    link: Optional[str] = Field(
        default=None,
        description="Link to share the desktop. None if no share link has been generated yet.",
    )
