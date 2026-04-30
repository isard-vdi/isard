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


class DownloadsProcessed(RethinkSharedConnection):
    """Data-access layer for the admin "registry downloads" flow.

    The admin downloads service (``services/admin/downloads.py``)
    matches a remote registry's catalogue against the local
    ``domains``, ``media``, ``videos``, ``virt_install`` and
    ``viewers`` tables. The queries here back that matching - they
    are intentionally generic over ``kind`` because the registry
    metadata format is the same across tables.

    Per the framework-agnostic rule: this layer returns plain
    ``list[dict]`` / ``dict``; the service decides how to fold them
    into the response payload.
    """

    @classmethod
    def list_user_kind_downloads(cls, kind: str, user_id: str) -> list[dict]:
        """Return the rows in ``kind`` (``domains`` / ``media``) owned
        by ``user_id`` that carry a non-falsey ``url-isard``.

        Used to mark catalogue entries as "already downloaded" against
        the running stack. ``has_fields`` short-circuits the filter so
        rows without the registry marker are excluded from the result.
        """
        with cls._rdb_context():
            return list(
                r.table(kind)
                .get_all(user_id, index="user")
                .has_fields("url-isard")
                .filter(~r.row["url-isard"].eq(False))
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_user_media_url_web_downloads(cls, user_id: str) -> list[dict]:
        """Return ``media`` rows owned by ``user_id`` that carry a
        non-falsey ``url-web``.

        Sibling to :meth:`list_user_kind_downloads` for media: a media
        row may have been registered via the registry's ``url-web``
        rather than ``url-isard`` (alternate download URL). Both lists
        feed the catalogue-merge step.
        """
        with cls._rdb_context():
            return list(
                r.table("media")
                .get_all(user_id, index="user")
                .has_fields("url-web")
                .filter(~r.row["url-web"].eq(False))
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_table_rows(cls, kind: str) -> list[dict]:
        """Return every row of ``kind`` (used for non-user-scoped
        catalogues such as ``virt_install`` / ``videos`` / ``viewers``).

        These tables are global, so the matching step does not filter
        by user. Returning the full table is small (handfuls of rows
        per kind) - no pagination is required here.
        """
        with cls._rdb_context():
            return list(r.table(kind).run(cls._rdb_connection))

    @classmethod
    def list_video_ids(cls) -> list[str]:
        """Return every ``id`` from the ``videos`` table.

        Backs the missing-resource probe in the domain-download flow:
        if a registry domain references a video id we don't have, the
        service inserts the missing row before the download.
        """
        with cls._rdb_context():
            rows = list(r.table("videos").pluck("id").run(cls._rdb_connection))
        return [row["id"] for row in rows]

    @classmethod
    def find_user_kind_by_url(
        cls, kind: str, user_id: str, url_isard: str
    ) -> list[dict]:
        """Return rows in ``kind`` owned by ``user_id`` whose
        ``url-isard`` index matches ``url_isard``.

        Used to detect "this domain/media is already downloaded under
        another id" so the service can either re-use the existing row
        or mint a new id.
        """
        with cls._rdb_context():
            return list(
                r.table(kind)
                .get_all(url_isard, index="url-isard")
                .filter({"user": user_id})
                .run(cls._rdb_connection)
            )

    @classmethod
    def find_user_kind_by_url_web(
        cls, kind: str, user_id: str, url_web: str
    ) -> list[dict]:
        """Return rows in ``kind`` owned by ``user_id`` whose
        ``url-web`` index matches ``url_web``.

        Sibling to :meth:`find_user_kind_by_url` for media rows that
        were registered via the alternate ``url-web`` registry path.
        """
        with cls._rdb_context():
            return list(
                r.table(kind)
                .get_all(url_web, index="url-web")
                .filter({"user": user_id})
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_metadata(cls, user_id: str) -> dict:
        """Return the user metadata fields stamped on download records.

        Plucks ``id``, ``category``, ``group``, ``provider``,
        ``username``, ``uid`` so download rows carry the owner context
        the engine and stats pipeline rely on. Returns the raw row
        - the service shapes the dict for the download record.
        """
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .pluck("id", "category", "group", "provider", "username", "uid")
                .run(cls._rdb_connection)
            )
