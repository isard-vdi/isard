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

Mirrors :mod:`api_viewers_config`: read, write and invalidate the singleton
``config`` row. Holds the main-domain certificate configuration, e.g.::

    config[1].certificates.main_domain = {
        "names": ["vdi.example.com"],       # ordered; names[0] is the primary
        "certificate_source": "acme",
        "email": "ops@example.com",
        "acme_server": "letsencrypt",
    }

``names`` is a list rather than a single string because the shape is what is
expensive to change later, not the feature: a stored string would need a
migration over live data plus a compatibility window in every reader. It is
ordered, and ``names[0]`` carries weight — acme.sh indexes a certificate by its
first name, which decides the on-disk directory and the deploy key.

This helper only persists configuration. Issuance is driven elsewhere.
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
        """Merge-write ``config[1].certificates`` and invalidate the cache.

        RethinkDB's ``update`` is a deep merge, so this persists a subset
        without disturbing sibling keys. It can never remove one — use
        :meth:`replace_certificates_config` when a block has to shrink.
        """
        with cls._rdb_context():
            r.table("config").get(1).update({"certificates": certificates}).run(
                cls._rdb_connection
            )
        Caches.invalidate_cache("config", 1)

    @classmethod
    def replace_certificates_config(cls, certificates: dict) -> None:
        """Replace ``config[1].certificates`` wholesale, dropping removed keys.

        ``r.literal`` forces a replace of the whole subtree, which is the only
        way a nested block can actually shrink. The flip side is that every key
        the caller does not resend is deleted, so callers must hand over the
        complete document they want to end up with.
        """
        with cls._rdb_context():
            r.table("config").get(1).update(
                {"certificates": r.literal(certificates)}
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("config", 1)
