#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from pydantic import BaseModel, RootModel


class VpnConnectionRequest(BaseModel):
    """Request for VPN connection update"""

    remote_ip: str
    remote_port: int


class VpnDisconnectListItem(BaseModel):
    """Single VPN disconnect item"""

    kind: str
    client_ip: str


class VpnDisconnectListRequest(RootModel[List[VpnDisconnectListItem]]):
    """Request to disconnect multiple VPN connections"""

    pass
