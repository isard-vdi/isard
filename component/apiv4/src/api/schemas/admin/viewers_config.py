#
#   Copyright © 2025 IsardVDI
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

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ViewerConfigUpdateRequest(BaseModel):
    """Request to update a viewer custom configuration"""

    custom: Optional[str] = None


class ViewerConfigItem(BaseModel):
    """Single viewer configuration row.

    Fields match the per-viewer dict stored under ``config.viewers`` in
    RethinkDB and consumed by the webapp DataTables admin view.
    """

    key: Optional[str] = None
    viewer: Optional[str] = None
    custom: Optional[str] = None
    default: Optional[str] = None
    fixed: Optional[str] = None


class RdpSecurityConfig(BaseModel):
    """Which security levels a guest RDP may serve, and how RDP files check its certificate."""

    allowed_protocols: list[Literal["rdp", "tls", "nla"]] = Field(
        min_length=1,
        description=(
            "Security levels a guest RDP may negotiate for its RDP viewers to open:"
            " rdp (standard RDP security, no TLS), tls and nla. A guest that"
            " negotiates a level not listed is refused for every RDP viewer."
            " All three by default."
        ),
    )
    certificate_check: Optional[Literal[0, 1, 2]] = Field(
        default=None,
        description=(
            "``authentication level`` of the RDP files: 0 connects without warning"
            " about a guest certificate it cannot verify, 1 does not connect, 2 warns."
            " Read from and written to the custom part of file_rdpgw and file_rdpvpn;"
            " null leaves them as they are."
        ),
    )
