#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer
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

import logging as log

from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers

from .base import BaseHandler, json_dumps


class RecycleBinHandler(BaseHandler):

    async def _emit_user_admin(self, event, payload, owner_id):
        await self.emit(
            event, json_dumps(payload), namespace="/userspace", room=owner_id
        )
        await self.emit(
            event, json_dumps(payload), namespace="/administrators", room="admins"
        )

    def _build_add_payload(self, rb_id, owner_id):
        # Per-key cache invalidation so a single rcb update doesn't blow
        # the cache for every other rcb (the pre-fix path called
        # ``cache_clear()`` on every per-row event, leaving the 60s TTL
        # effectively useless under any concurrency).
        RecycleBinHelpers.clear_get_count_for(rb_id)
        RecycleBinHelpers.clear_get_user_amount_for(owner_id)
        payload = RecycleBinHelpers.get_count(rb_id)
        payload["items_in_bin"] = RecycleBinHelpers.get_user_amount(owner_id)
        return payload

    def _build_count_payload(self, rb_id):
        RecycleBinHelpers.clear_get_count_for(rb_id)
        return RecycleBinHelpers.get_count(rb_id)

    def _prop(self, val, key, default=None):
        attr = getattr(val, key, None)
        if attr is not None:
            return attr
        return (val.additional_properties or {}).get(key, default)

    async def on_insert(self, new_val):
        owner_id = self._prop(new_val, "owner_id")
        if not owner_id:
            return
        payload = self._build_add_payload(self._prop(new_val, "id"), owner_id)
        await self._emit_user_admin("add_recycle_bin", payload, owner_id)

    async def on_update(self, old_val, new_val):
        owner_id = self._prop(new_val, "owner_id")
        if not owner_id:
            return
        if not self._prop(old_val, "owner_id"):
            payload = self._build_add_payload(self._prop(new_val, "id"), owner_id)
            await self._emit_user_admin("add_recycle_bin", payload, owner_id)
            return
        old_status = self._prop(old_val, "status")
        new_status = self._prop(new_val, "status")
        if old_status != new_status:
            event = (
                "delete_recycle_bin"
                if new_status == "deleted"
                else "update_recycle_bin"
            )
            await self._emit_user_admin(
                event,
                {"id": self._prop(new_val, "id"), "status": new_status},
                owner_id,
            )
            return
        payload = self._build_count_payload(self._prop(new_val, "id"))
        await self._emit_user_admin("update_recycle_bin", payload, owner_id)

    async def on_delete(self, old_val):
        owner_id = self._prop(old_val, "owner_id")
        if not owner_id:
            return
        await self._emit_user_admin(
            "delete_recycle_bin",
            {
                "id": self._prop(old_val, "id"),
                "status": self._prop(old_val, "status", "deleted"),
            },
            owner_id,
        )
