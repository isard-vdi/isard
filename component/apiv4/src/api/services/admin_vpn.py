#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback
from typing import List

from api.schemas.vpn import VpnDisconnectListItem
from api.services.error import Error
from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


class AdminVpnService:
    """Service for admin VPN connection management."""

    @staticmethod
    def active_client(kind, client_ip, remote_ip=None, remote_port=None, status=False):
        """Update or query VPN client connection status.

        Route layer constrains ``kind`` via ``Literal["users", "hypers"]``.
        """
        connection_data = {
            "connected": status,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
        }

        if kind == "users":
            with RethinkSharedConnection._rdb_context():
                if len(
                    list(
                        r.table("remotevpn")
                        .get_all(client_ip, index="wg_client_ip")
                        .run(RethinkSharedConnection._rdb_connection)
                    )
                ):
                    r.table("remotevpn").get_all(
                        client_ip, index="wg_client_ip"
                    ).update({"vpn": {"wireguard": connection_data}}).run(
                        RethinkSharedConnection._rdb_connection
                    )
                    return True

            # Try users table
            with RethinkSharedConnection._rdb_context():
                result = list(
                    r.table("users")
                    .get_all(client_ip, index="wg_client_ip")
                    .run(RethinkSharedConnection._rdb_connection)
                )
            if not result:
                return False
            with RethinkSharedConnection._rdb_context():
                r.table("users").get_all(client_ip, index="wg_client_ip").update(
                    {"vpn": {"wireguard": connection_data}}
                ).run(RethinkSharedConnection._rdb_connection)
            return True
        else:  # hypers
            with RethinkSharedConnection._rdb_context():
                r.table("hypervisors").get_all(client_ip, index="wg_client_ip").update(
                    {"vpn": {"wireguard": connection_data}}
                ).run(RethinkSharedConnection._rdb_connection)
            return True

    @staticmethod
    def reset_connection_status(kind):
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
            with RethinkSharedConnection._rdb_context():
                r.table("users").has_fields({"vpn": {"wireguard": "Address"}}).update(
                    {"vpn": {"wireguard": connection_data}}
                ).run(RethinkSharedConnection._rdb_connection)
        if kind in ["remotevpn", "all"]:
            with RethinkSharedConnection._rdb_context():
                r.table("remotevpn").has_fields(
                    {"vpn": {"wireguard": "Address"}}
                ).update({"vpn": {"wireguard": connection_data}}).run(
                    RethinkSharedConnection._rdb_connection
                )
        if kind in ["hypers", "all"]:
            with RethinkSharedConnection._rdb_context():
                r.table("hypervisors").has_fields(
                    {"vpn": {"wireguard": "Address"}}
                ).update({"vpn": {"wireguard": connection_data}}).run(
                    RethinkSharedConnection._rdb_connection
                )
        return True

    @staticmethod
    def reset_connections_list_status(peers: List[VpnDisconnectListItem]):
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
            with RethinkSharedConnection._rdb_context():
                r.table("users").get_all(
                    r.args(users_vpn_ips), index="wg_client_ip"
                ).update({"vpn": {"wireguard": connection_data}}).run(
                    RethinkSharedConnection._rdb_connection
                )
            with RethinkSharedConnection._rdb_context():
                r.table("remotevpn").get_all(
                    r.args(users_vpn_ips), index="wg_client_ip"
                ).update({"vpn": {"wireguard": connection_data}}).run(
                    RethinkSharedConnection._rdb_connection
                )

        hypers_vpn_ips = [p.client_ip for p in peers if p.kind == "hypers"]
        if len(hypers_vpn_ips):
            with RethinkSharedConnection._rdb_context():
                r.table("hypervisors").get_all(
                    r.args(hypers_vpn_ips), index="wg_client_ip"
                ).update({"vpn": {"wireguard": connection_data}}).run(
                    RethinkSharedConnection._rdb_connection
                )
        return True
