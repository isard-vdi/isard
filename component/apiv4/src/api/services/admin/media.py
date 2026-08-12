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

from isardvdi_common.lib.media.media import MediaProcessed
from isardvdi_common.lib.task_index import MEDIA, last_task_ids
from isardvdi_common.models.task import Task


class AdminMediaService:

    @staticmethod
    def get_media_status(payload: dict) -> list:
        """Get media status counts, scoped by category for managers."""
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return MediaProcessed.admin_get_media_status_count(category_id=category_id)

    @staticmethod
    def get_media(payload: dict, status: str = None) -> list:
        """Get media list, optionally filtered by status."""
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        rows = MediaProcessed.admin_get_media(status=status, category_id=category_id)
        # Same contract as the storage listing: the media table's "last task
        # info" button read the retired scalar. Media tasks live under their own
        # index namespace, hence ``kind=MEDIA``.
        last = last_task_ids(Task._redis, [row.get("id") for row in rows], kind=MEDIA)
        for row in rows:
            row["last_task_id"] = last.get(row.get("id"))
        return rows
