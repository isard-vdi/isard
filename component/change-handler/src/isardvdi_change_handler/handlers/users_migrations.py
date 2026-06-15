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

from .base import BaseHandler, json_dumps


class UsersMigrationsHandler(BaseHandler):
    """Keeps the admin datatable live (``users_migrations_*`` on
    ``/administrators``) and also streams import progress to the importing
    user's own ``/userspace`` room so the migration view can follow it."""

    def _target_user(self, val):
        # All record fields (origin_user, target_user, status, migrated_*)
        # live in additional_properties on the generated row model.
        return (val.additional_properties or {}).get("target_user")

    async def on_insert(self, new_val):
        await super().on_insert(new_val)
        await self._emit_progress(new_val)

    async def on_update(self, old_val, new_val):
        await super().on_update(old_val, new_val)
        await self._emit_progress(new_val)

    async def _emit_progress(self, new_val):
        target_user = self._target_user(new_val)
        if not target_user:
            return
        await self.emit(
            "user_migration_data", json_dumps(new_val), "/userspace", target_user
        )
