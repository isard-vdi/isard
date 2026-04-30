#
#   Copyright © 2026 IsardVDI
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

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


class VpnProcessed(RethinkSharedConnection):
    """Data-access layer for the wireguard VPN connection-status fields
    on the ``users``, ``remotevpn`` and ``hypervisors`` tables.

    Different from ``isardvdi_common.helpers.isard_vpn`` (client-side
    cert/config generation): this class only owns the inline rdb
    queries that the apiv4 ``services/admin/vpn.py`` layer used to
    embed.

    All three target tables expose the same ``wg_client_ip`` index;
    the methods here lean on that consistency to avoid bespoke per-table
    helpers.
    """

    @classmethod
    def update_connection_by_client_ip(
        cls,
        table: str,
        client_ip: str,
        connection_data: dict,
    ) -> None:
        """Update the ``vpn.wireguard`` block on every row whose
        ``wg_client_ip`` index matches ``client_ip``.

        Rdb's ``update`` is a no-op when the index returns zero rows,
        so callers that need to act on the "no row matched" branch must
        first probe with :meth:`exists_by_client_ip`.
        """
        with cls._rdb_context():
            r.table(table).get_all(client_ip, index="wg_client_ip").update(
                {"vpn": {"wireguard": connection_data}}
            ).run(cls._rdb_connection)

    @classmethod
    def exists_by_client_ip(cls, table: str, client_ip: str) -> bool:
        """Return ``True`` if at least one row in ``table`` matches
        ``client_ip`` on the ``wg_client_ip`` index.

        Used by the service to short-circuit between the ``remotevpn``
        and ``users`` tables (a client_ip lives in exactly one of them).
        """
        with cls._rdb_context():
            hits = list(
                r.table(table)
                .get_all(client_ip, index="wg_client_ip")
                .limit(1)
                .run(cls._rdb_connection)
            )
        return bool(hits)

    @classmethod
    def reset_connections_for_table(cls, table: str, connection_data: dict) -> None:
        """Reset ``vpn.wireguard`` on every row of ``table`` that has a
        wireguard ``Address`` field.

        ``has_fields({"vpn": {"wireguard": "Address"}})`` is the legacy
        marker that the row was ever associated to a wireguard peer;
        rows without it are skipped.
        """
        with cls._rdb_context():
            r.table(table).has_fields({"vpn": {"wireguard": "Address"}}).update(
                {"vpn": {"wireguard": connection_data}}
            ).run(cls._rdb_connection)

    @classmethod
    def reset_connections_for_client_ips(
        cls,
        table: str,
        client_ips: list[str],
        connection_data: dict,
    ) -> None:
        """Reset ``vpn.wireguard`` on every row of ``table`` whose
        ``wg_client_ip`` is in ``client_ips``.

        Caller filters the list to non-empty before invoking — rdb's
        ``r.args`` on an empty list returns no rows so the call is a
        no-op, but the explicit guard at the call site keeps the
        intent clear.
        """
        with cls._rdb_context():
            r.table(table).get_all(r.args(client_ips), index="wg_client_ip").update(
                {"vpn": {"wireguard": connection_data}}
            ).run(cls._rdb_connection)
