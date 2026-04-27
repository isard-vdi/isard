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


from isardvdi_common.lib.media.media import MediaProcessed
from isardvdi_common.models.media import Media
from isardvdi_common.schemas.media import MediaStatusEnum

from .base import BaseHandler, json_dumps


class MediaHandler(BaseHandler):

    def _with_editable(self, val):
        enriched = val.model_copy()
        enriched.additional_properties = {
            **(val.additional_properties or {}),
            "editable": True,
        }
        return enriched

    def _enrich(self, val):
        extra = MediaProcessed.get_media_user_group_and_category_name(val.id)
        enriched = val.model_copy()
        enriched.additional_properties = {
            **(val.additional_properties or {}),
            **extra,
        }
        return enriched

    async def on_insert(self, new_val):
        await self.emit(
            "media_add",
            json_dumps(self._with_editable(new_val)),
            namespace="/userspace",
            room=new_val.user,
        )
        await self.emit(
            "media_add",
            json_dumps(new_val),
            namespace="/administrators",
            room=new_val.category,
        )
        await super().on_insert(new_val)

    async def on_update(self, old_val, new_val):
        if new_val.status == MediaStatusEnum.deleted.value:
            await self.on_delete(new_val)
            return
        enriched = self._enrich(new_val)
        await self.emit(
            "media_update",
            json_dumps(self._with_editable(enriched)),
            namespace="/userspace",
            room=new_val.user,
        )
        await self.emit(
            "media_update",
            json_dumps(enriched),
            namespace="/administrators",
            room=new_val.category,
        )
        await super().on_update(old_val, enriched)
        if new_val.status == MediaStatusEnum.download_failed_invalid_format.value and (
            old_val is None
            or old_val.status != MediaStatusEnum.download_failed_invalid_format.value
        ):
            Media(new_val.id).delete_file(user_id=new_val.user, keep_status=True)

    async def on_delete(self, old_val):
        await self.emit(
            "media_delete",
            json_dumps(self._with_editable(old_val)),
            namespace="/userspace",
            room=old_val.user,
        )
        await self.emit(
            "media_delete",
            json_dumps(old_val),
            namespace="/administrators",
            room=old_val.category,
        )
        await super().on_delete(old_val)
