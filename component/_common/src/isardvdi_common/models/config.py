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

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r

_get_config_cache: TTLCache = TTLCache(maxsize=10, ttl=1)


class Config(RethinkCustomBase):

    _rdb_table = "config"

    @classmethod
    @cached(cache=_get_config_cache)
    def get_config(cls):
        """
        Get the configuration from the database.
        """
        with cls._rdb_context():
            config = r.table(cls._rdb_table).get(1).run(cls._rdb_connection)

        if not config:
            return None

        return config

    @classmethod
    def clear_get_config_cache(cls):
        _get_config_cache.clear()

    @classmethod
    def get_user_migration_config(cls):
        """
        Get the user migration configuration.
        """
        config = cls.get_config()
        if not config or "user_migration" not in config:
            return {}

        return config["user_migration"]

    @classmethod
    def set_user_migration_config(cls, data: dict) -> dict:
        """Replace the ``user_migration`` block in the config row.

        Clears the ``get_config`` cache after the update so the next read
        sees fresh data, and returns the post-update value.
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(1).update({"user_migration": data}).run(
                cls._rdb_connection
            )
        cls.clear_get_config_cache()
        return cls.get_user_migration_config()

    @classmethod
    def get_provider_config(cls, provider: str):
        config = cls.get_config()
        if not config["auth"].get(provider):
            raise Error(
                "not_found",
                f"Provider configuration for '{provider}' not found.",
            )

        if "migration" in config and "notification_bar" in config["migration"]:
            try:
                with cls._rdb_context():
                    config["migration"]["notification_bar"]["template_name"] = (
                        r.table("notification_tmpls")
                        .get(config["migration"]["notification_bar"]["template"])[
                            "name"
                        ]
                        .run(cls._rdb_connection)
                    )
            except r.ReqlNonExistenceError:
                config["template_name"] = "[DELETED]"
        return config["auth"].get(provider)
