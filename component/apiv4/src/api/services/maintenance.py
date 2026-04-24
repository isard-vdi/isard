#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from isardvdi_common.helpers.maintenance import Maintenance


class MaintenanceService:

    @staticmethod
    def is_enabled():
        return Maintenance.enabled

    @staticmethod
    def get_category_status(category_id: str) -> bool:
        """
        Get the maintenance status for a specific category.
        :param category_id: The ID of the category to check.
        :return: True if the category is under maintenance, False otherwise.
        """
        return Maintenance.category_enabled(category_id)

    @staticmethod
    def set_enabled(enabled: bool):
        """
        Set the maintenance status of the API.
        :param enabled: True to enable maintenance, False to disable it.
        """
        Maintenance.enabled = enabled

    @staticmethod
    def update_text(text: dict):
        """
        Update the maintenance text.
        :param text: The new text to display during maintenance.
        """
        Maintenance.update_text(text.model_dump(mode="json"))

    @staticmethod
    def get_text() -> str:
        """
        Get the current maintenance text.
        :return: The text to display during maintenance.
        """
        return Maintenance.get_text()
