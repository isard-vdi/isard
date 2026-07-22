#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List, Optional

from api.schemas.vpn import VpnDisconnectListItem
from isardvdi_common.lib.vpn.vpn import VpnProcessed


class AdminVpnService:
    """Service for admin VPN connection management."""

    @staticmethod
    def active_client(
        kind: str,
        client_ip: str,
        remote_ip: Optional[str] = None,
        remote_port: Optional[int] = None,
        status: bool = False,
    ) -> bool:
        """Update or query VPN client connection status.

        Route layer constrains ``kind`` via ``Literal["users", "hypers"]``.
        """
        connection_data = {
            "connected": status,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
        }

        if kind == "users":
            # remotevpn rows take precedence; if a peer has been issued
            # via remotevpn we update that row and stop. Otherwise fall
            # back to the users table.
            if VpnProcessed.exists_by_client_ip("remotevpn", client_ip):
                VpnProcessed.update_connection_by_client_ip(
                    "remotevpn", client_ip, connection_data
                )
                return True

            if not VpnProcessed.exists_by_client_ip("users", client_ip):
                return False
            VpnProcessed.update_connection_by_client_ip(
                "users", client_ip, connection_data
            )
            return True

        # hypers
        VpnProcessed.update_connection_by_client_ip(
            "hypervisors", client_ip, connection_data
        )
        return True

    @staticmethod
    def reset_connection_status(kind: str) -> bool:
        """Reset VPN connection status for a kind.

        Route layer constrains ``kind`` to ``Literal["all"]`` today.
        The service still branches on ``users`` / ``hypers`` because
        internal callers may pass those.
        """
        connection_data = {
            "connected": False,
            "remote_ip": None,
            "remote_port": None,
        }

        if kind in ["users", "all"]:
            VpnProcessed.reset_connections_for_table("users", connection_data)
        if kind in ["remotevpn", "all"]:
            VpnProcessed.reset_connections_for_table("remotevpn", connection_data)
        if kind in ["hypers", "all"]:
            VpnProcessed.reset_connections_for_table("hypervisors", connection_data)
        return True

    @staticmethod
    def reset_connections_list_status(peers: List[VpnDisconnectListItem]) -> bool:
        """Reset VPN connection status for a typed list of peers.

        Accepts ``VpnDisconnectListItem`` models directly so the
        ``kind`` and ``client_ip`` contract is enforced at the service
        boundary, not only at the route layer.
        """
        connection_data = {
            "connected": False,
            "remote_ip": None,
            "remote_port": None,
        }
        users_vpn_ips = [p.client_ip for p in peers if p.kind == "users"]
        if len(users_vpn_ips):
            VpnProcessed.reset_connections_for_client_ips(
                "users", users_vpn_ips, connection_data
            )
            VpnProcessed.reset_connections_for_client_ips(
                "remotevpn", users_vpn_ips, connection_data
            )

        hypers_vpn_ips = [p.client_ip for p in peers if p.kind == "hypers"]
        if len(hypers_vpn_ips):
            VpnProcessed.reset_connections_for_client_ips(
                "hypervisors", hypers_vpn_ips, connection_data
            )
        return True
