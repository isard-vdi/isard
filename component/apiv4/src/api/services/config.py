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
from isardvdi_common.models.config import Config


class ConfigService:

    @staticmethod
    def get_config():
        """
        Get the configuration from the database.
        """
        config = Config.get_config()
        if not config:
            raise Error(
                "not_found",
                "Configuration not found.",
            )
        return config

    @staticmethod
    def get_login_config():
        """
        Get the login configuration from the database.
        """
        config = ConfigService.get_config()
        if not config:
            raise Error(
                "not_found",
                "Login configuration not found.",
            )

        login_config = config.get("login")

        for key in ["notification_cover", "notification_form"]:
            if key in login_config and type(login_config[key]) is dict:
                for field in ["description", "title", "text", "url"]:
                    if (
                        "button" in login_config[key]
                        and field in login_config[key]["button"]
                        and login_config[key]["button"][field] is not None
                    ):
                        login_config[key]["button"][field] = html.unescape(
                            login_config[key]["button"][field]
                        )
                    if (
                        field in login_config[key]
                        and login_config[key][field] is not None
                    ):
                        login_config[key][field] = html.unescape(
                            login_config[key][field]
                        )

        return login_config

    @staticmethod
    def get_user_migration_config():
        """
        Get the user migration configuration from the database.
        """
        config = Config.get_user_migration_config()
        return config

    @staticmethod
    def get_provider_config(provider: str):
        """
        Get the provider configuration from the database.
        """
        config = Config.get_provider_config(provider)
        return config
