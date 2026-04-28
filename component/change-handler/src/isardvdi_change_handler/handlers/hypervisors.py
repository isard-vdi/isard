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

import logging as log

from isardvdi_common.models.hypervisor import Hypervisor
from isardvdi_common.schemas.hypervisor import HypervisorStatusEnum

from .base import BaseHandler, json_dumps


class HypervisorsHandler(BaseHandler):

    async def on_insert(self, new_val):
        data = Hypervisor.get_hypervisor(new_val.id)
        if data is None:
            log.info(
                "Hypervisor %s no longer exists; skipping socket event", new_val.id
            )
            return
        data["desktops_started"] = Hypervisor.count_started_desktops(data["id"])
        await self.emit("hyper_data", json_dumps(data), "/administrators", "admins")

    async def on_update(self, old_val, new_val):
        if old_val.status != new_val.status:
            data = Hypervisor.get_hypervisor(new_val.id)
            if data is None:
                log.info(
                    "Hypervisor %s no longer exists; skipping socket event", new_val.id
                )
                return
            data["desktops_started"] = Hypervisor.count_started_desktops(data["id"])
            await self.emit("hyper_data", json_dumps(data), "/administrators", "admins")
            return

        enriched = new_val.model_copy()
        if new_val.status != HypervisorStatusEnum.online.value:
            desktops_started = 0
        else:
            desktops_started = Hypervisor.count_started_desktops(new_val.id)
        enriched.additional_properties = {
            **(new_val.additional_properties or {}),
            "desktops_started": desktops_started,
        }
        await self.emit("hyper_data", json_dumps(enriched), "/administrators", "admins")

    async def on_delete(self, old_val):
        await self.emit(
            "hyper_deleted", json_dumps(old_val), "/administrators", "admins"
        )
