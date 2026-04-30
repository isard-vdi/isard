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

from api.services.login_config_cache import clear_login_config_cache
from isardvdi_common.models.config import Config


class AdminLoginConfigService:

    @staticmethod
    def update_login_notification(data: dict) -> None:
        if Config.update_login_notification(data):
            clear_login_config_cache()

    @staticmethod
    def enable_login_notification(notification_type: str, enable: bool) -> None:
        Config.enable_login_notification(notification_type, enable)
        clear_login_config_cache()
