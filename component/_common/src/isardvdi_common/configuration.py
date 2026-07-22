#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Simó Albert i Beltran
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

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.provider_config import (
    provider_config_api_to_db,
    provider_config_db_to_api,
)


class Configuration(RethinkCustomBase):
    """
    Manage Configuration

    Use constructor with keyword arguments to modify the configuration or use the object
    attributes to get or modify the configuration.
    """

    _rdb_table = "config"

    def __init__(self, id=None):
        super().__init__(1)

    def __getattr__(self, name):
        """
        Get an attribute from Configuration.

        When getting the 'auth' attribute, converts provider config fields
        from DB format (comma-separated strings) to API format (lists).
        """
        value = super().__getattr__(name)
        if name == "auth" and value:
            for provider_data in value.values():
                if isinstance(provider_data, dict):
                    for v in provider_data.values():
                        if isinstance(v, dict):
                            provider_config_db_to_api(v)
        return value

    def __setattr__(self, name, value):
        """
        Set an attribute on Configuration.

        When setting the 'auth' attribute, converts provider config fields
        from API format (lists) to DB format (comma-separated strings).
        """
        if name == "auth" and value:
            for provider_data in value.values():
                if isinstance(provider_data, dict):
                    for v in provider_data.values():
                        if isinstance(v, dict):
                            provider_config_api_to_db(v)
        super().__setattr__(name, value)
