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

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


class AdminLoginConfigService(RethinkSharedConnection):

    _rdb_table = "config"

    @classmethod
    def update_login_notification(cls, data: dict) -> None:
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
                return

            # r.literal() replaces the whole 'login' dict instead of merging, so
            # keys present in DB but not in `current` are dropped cleanly (we
            # already carry them through via the read-merge-write above).
            r.table(cls._rdb_table).get(1).update({"login": r.literal(current)}).run(
                cls._rdb_connection
            )

        from api.routes.open import clear_login_config_cache

        clear_login_config_cache()

    @classmethod
    def enable_login_notification(cls, notification_type: str, enable: bool) -> None:
        with cls._rdb_context():
            r.table(cls._rdb_table).get(1).update(
                {"login": {f"notification_{notification_type}": {"enabled": enable}}}
            ).run(cls._rdb_connection)

        from api.routes.open import clear_login_config_cache

        clear_login_config_cache()
