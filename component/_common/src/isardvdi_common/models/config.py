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
    def update_login_notification(cls, data: dict) -> bool:
        """Read-merge-write the ``login.notification_{cover,form}`` blocks.

        ``data`` is a dict with optional ``cover`` / ``form`` keys; each
        sub-dict supplies the new notification config. The ``enabled``
        flag falls back to the existing DB value when omitted (so the
        caller can edit content without re-asserting state).

        Uses ``r.literal()`` so the merge replaces the whole ``login``
        dict instead of unioning — keys present in DB but absent from
        ``current`` are dropped cleanly.

        Returns ``True`` if the DB was updated, ``False`` if ``data``
        contained nothing to apply. Clears the ``get_config`` cache on
        write; service-side caches must be cleared by the caller.
        """
        with cls._rdb_context():
            current = (
                r.table(cls._rdb_table)
                .get(1)
                .get_field("login")
                .default({})
                .run(cls._rdb_connection)
            )

            changed = False
            for position, key in (
                ("cover", "notification_cover"),
                ("form", "notification_form"),
            ):
                position_data = data.get(position)
                if position_data is None:
                    continue
                if "enabled" not in position_data:
                    position_data["enabled"] = current.get(key, {}).get(
                        "enabled", False
                    )
                current[key] = position_data
                changed = True

            if not changed:
                return False

            r.table(cls._rdb_table).get(1).update({"login": r.literal(current)}).run(
                cls._rdb_connection
            )

        cls.clear_get_config_cache()
        return True

    @classmethod
    def update_old_tasks(cls, updates: dict) -> None:
        """Partial-update the ``old_tasks`` config block.

        ``updates`` is a flat dict of keys to set inside ``old_tasks``
        (e.g. ``{"older_than": 86400, "enabled": True}``). Other keys
        in the existing ``old_tasks`` block are preserved.

        Clears the get_config cache after the write.
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(1).update({"old_tasks": updates}).run(
                cls._rdb_connection
            )
        cls.clear_get_config_cache()

    @classmethod
    def get_old_tasks_config(cls) -> dict:
        """Read the ``old_tasks`` config block.

        Returns an empty dict when the field is missing — callers fall
        back to defaults rather than seeing the rdb error.
        """
        try:
            with cls._rdb_context():
                return (
                    r.table(cls._rdb_table)
                    .get(1)
                    .get_field("old_tasks")
                    .default({})
                    .run(cls._rdb_connection)
                )
        except Exception:
            return {}

    @classmethod
    def enable_login_notification(cls, notification_type: str, enable: bool) -> None:
        """Toggle ``login.notification_<type>.enabled`` on/off.

        ``notification_type`` is ``"cover"`` or ``"form"`` (Literal-shaped
        but kept untyped here so the `_common` boundary stays loose;
        the route validates it). Clears the ``get_config`` cache after
        the write; service-side caches must be cleared by the caller.
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(1).update(
                {"login": {f"notification_{notification_type}": {"enabled": enable}}}
            ).run(cls._rdb_connection)

        cls.clear_get_config_cache()

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
