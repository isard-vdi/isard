#
#   Copyright © 2026 Josep Maria Viñolas Auquer
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
"""Deployment-wide certificate configuration in ``config[1].certificates``.

Canonical note on the config shape: ``main_domain.names`` is ordered and
``names[0]`` is the primary. acme.sh indexes a certificate by its first name,
which decides the on-disk directory and the deploy key, so reordering describes
a different certificate. This helper only persists configuration; issuance is
driven elsewhere.
"""

from isardvdi_common.helpers.caches import Caches
from rethinkdb import r

from ..connections.rethink_connection_factory import RethinkSharedConnection


class CertificatesConfig(RethinkSharedConnection):
    """Read/write the global ``config[1].certificates`` block."""

    @classmethod
    def get_certificates_config(cls) -> dict:
        """Return ``config[1].certificates`` (``{}`` when absent)."""
        with cls._rdb_context():
            config_row = r.table("config").get(1).default({}).run(cls._rdb_connection)
        return (config_row or {}).get("certificates") or {}

    @classmethod
    def update_certificates_config(cls, certificates: dict) -> None:
        """Merge-write ``config[1].certificates`` (deep merge; cannot remove keys,
        use :meth:`replace_certificates_config` to shrink)."""
        with cls._rdb_context():
            r.table("config").get(1).update({"certificates": certificates}).run(
                cls._rdb_connection
            )
        Caches.invalidate_cache("config", 1)

    @classmethod
    def replace_certificates_config(cls, certificates: dict) -> None:
        """Replace ``config[1].certificates`` wholesale via ``r.literal``: every key
        the caller does not resend is deleted, so hand over the complete document."""
        with cls._rdb_context():
            r.table("config").get(1).update(
                {"certificates": r.literal(certificates)}
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("config", 1)
