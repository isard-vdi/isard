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

from isardvdi_common.schemas.domains import DesktopStatusEnum, Image
from pydantic import BaseModel, Field


class DesktopUpdateShareLinkRequest(BaseModel):
    enabled: bool = Field(
        default=True,
        description="If false, the share link will be disabled. If true, the share link will be enabled or regenerated.",
    )


class DesktopViewerScheduled(BaseModel):
    shutdown: Union[bool, str] = Field(
        default=False,
        description=(
            "When a shutdown is scheduled, contains the UTC end time as a "
            "'%Y-%m-%dT%H:%M%z' string. False when no shutdown is scheduled."
        ),
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
    # Connection details are absent while the desktop is in the
    # ``waiting_ip`` state — the guest hasn't reported its IP yet so the
    # service emits a stub ``{kind, protocol}`` payload and the client
    # is expected to poll until the IP arrives.
    viewer: Optional[str] = None
    urlp: Optional[str] = None
    cookie: Optional[str] = None
    values: Optional[BrowserRDPValues] = None


class FileRDPGWViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    name: Optional[str] = None
    ext: Optional[str] = None
    mime: Optional[str] = None
    content: Optional[str] = None


class FileRDPVPNViewer(BaseModel):
    kind: ViewerKind
    protocol: ViewerProtocol
    name: Optional[str] = None
    ext: Optional[str] = None
    mime: Optional[str] = None
    content: Optional[str] = None


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
    scheduled: Optional[DesktopViewerScheduled] = Field(
        default=None,
        description="Scheduled actions for the desktop viewer.",
    )
    viewers: ViewersModel = Field(
        description="List of available viewers for the desktop.",
    )
    image: Optional[Image] = Field(
        default=None,
        description="Desktop image (stock id or uploaded URL) used by the card.",
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
