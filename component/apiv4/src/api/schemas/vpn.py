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
    """Single VPN disconnect item.

    Matches the peer dict built by ``docker/vpn/src/wg_monitor.py``
    (around line 129): ``{"kind": <device>, "client_ip": <allowed_ip>}``.
    """

    kind: str
    client_ip: str


class AdminVpnConnectionsDisconnectRequest(RootModel[List[VpnDisconnectListItem]]):
    """Top-level JSON array body for ``DELETE /admin/vpn_connections``.

    Aligned with the FastAPI operation id ``vpn_connections_disconnect``.
    """

    pass
