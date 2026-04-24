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
import html

from api.services.error import Error
from isardvdi_common.lib.notifications.notifications_templates import (
    NotificationTemplatesProcessed,
)


class NotificationsTemplatesService:

    @staticmethod
    def get_disclaimer(user_id: str):
        """
        Get the disclaimer from the database.
        """
        disclaimer_template = NotificationTemplatesProcessed.get_disclaimer_template(
            user_id=user_id
        )
        if not disclaimer_template:
            raise Error(
                "not_found",
                "Disclaimer template not found.",
                description_code="not_found",
            )
        return disclaimer_template
