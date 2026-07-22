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

from isardvdi_common.lib.users.users.user import UsersProcessed

from .base import BaseHandler, json_dumps


class UsersHandler(BaseHandler):

    def _enrich(self, val):
        extra = UsersProcessed.get_user_role_group_and_category_name(val.id)
        enriched = val.model_copy()
        enriched.additional_properties = {
            **(val.additional_properties or {}),
            **extra,
        }
        return enriched

    async def on_insert(self, new_val):
        enriched = self._enrich(new_val)
        payload = json_dumps(enriched)
        await self.emit("users_data", payload, "/userspace", new_val.id)
        await self.emit("users_data", payload, "/administrators", "admins")
        await self.emit("users_data", payload, "/administrators", new_val.category)

    async def on_update(self, old_val, new_val):
        enriched = self._enrich(new_val)
        payload = json_dumps(enriched)
        await self.emit("users_data", payload, "/userspace", new_val.id)
        await self.emit("users_data", payload, "/administrators", "admins")
        await self.emit("users_data", payload, "/administrators", new_val.category)

    async def on_delete(self, old_val):
        payload = json_dumps(old_val)
        await self.emit("users_delete", payload, "/userspace", old_val.id)
        await self.emit("users_delete", payload, "/administrators", "admins")
        await self.emit("users_delete", payload, "/administrators", old_val.category)
