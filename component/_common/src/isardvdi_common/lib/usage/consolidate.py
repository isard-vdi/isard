#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Consolidator-level data access (usage_consumption insert, domains
pluck for deployment/template lookups). Per-item-type log fetchers
live in the sibling submodules."""

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r

# Module-level cache so writers can invalidate it after mutations.
_domains_cache: TTLCache = TTLCache(maxsize=1, ttl=120)


class ConsolidateProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the consolidator orchestrator."""

    @classmethod
    def insert_consumption_batch(cls, data: list[dict]) -> dict:
        """Bulk-insert ``usage_consumption`` rows with conflict=update.

        Soft durability — consolidations are reproducible from
        ``logs_*`` and the cost of a single durable fsync per row
        outweighs the value when consolidating a large day.
        """
        with cls._rdb_context():
            return (
                r.table("usage_consumption")
                .insert(data, conflict="update", durability="soft")
                .run(cls._rdb_connection)
            )

    @classmethod
    @cached(cache=_domains_cache, key=lambda cls: hashkey("domains"))
    def get_domains_with_tags(cls) -> dict:
        """Return ``{domain_id: [{name, tag, tag_name}, ...]}`` for all rows.

        The consolidator uses this to map a desktop_id back to its
        deployment tag / template name without per-row queries.
        Cached for 2 minutes so a single consolidation pass shares
        the lookup map.
        """
        with cls._rdb_context():
            return (
                r.table("domains")
                .pluck("id", "name", "tag", "tag_name")
                .group("id")
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_domains_with_tags_cache(cls) -> None:
        """Invalidate the domains-tag cache."""
        _domains_cache.clear()
