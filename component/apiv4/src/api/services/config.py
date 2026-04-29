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

        # Wrap pre-feature single-dict notifications into 1-item lists so the
        # frontend can iterate them uniformly. The per-category route already
        # returns lists (see admin_categories.get_login_config_for_category);
        # this is the global-only path. Without the wrap, Vue 3's
        # `v-for=(notification, index) in config?.notification_cover` runs over
        # the dict's values, none of which are notification objects, so no
        # notification ever renders on the public login page.
        for key in ("notification_cover", "notification_form"):
            notification = login_config.get(key)
            if isinstance(notification, dict):
                login_config[key] = [notification]
            elif notification is None:
                continue

        for key in ("notification_cover", "notification_form"):
            notification_list = login_config.get(key)
            if not notification_list:
                continue
            for notification in notification_list:
                if not isinstance(notification, dict):
                    continue
                for field in ("title", "description"):
                    if notification.get(field) is not None:
                        notification[field] = html.unescape(notification[field])
                button = notification.get("button")
                if isinstance(button, dict):
                    for field in ("text", "url"):
                        if button.get(field) is not None:
                            button[field] = html.unescape(button[field])

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
