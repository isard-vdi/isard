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
        return MediaProcessed.admin_get_media(status=status, category_id=category_id)
