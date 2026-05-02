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


import asyncio

from isardvdi_common.models.deployment import Deployment

from .base import BaseHandler, json_dumps


class DeploymentsHandler(BaseHandler):
    async def on_insert(self, new_val):
        deployment = await asyncio.to_thread(Deployment.get, new_val.id)
        await self.emit(
            "deployment_add",
            json_dumps(deployment),
            namespace="/userspace",
            room=new_val.user,
        )
        # await self.emit(
        #     "deployment_add",
        #     json_dumps(deployment),
        #     namespace="/administrators",
        #     room=deployment["category"],
        # ) # TODO
        await super().on_insert(new_val)

    async def on_update(self, old_val, new_val):
        await self.emit(
            "deployment_update",
            json_dumps(new_val),
            namespace="/userspace",
            room=new_val.user,
        )
        # await self.emit(
        #     "deployment_update",
        #     json_dumps(new_val),
        #     namespace="/administrators",
        #     room=new_val.category,
        # ) # TODO
        await super().on_update(old_val, new_val)

    async def on_delete(self, old_val):
        await self.emit(
            "deployment_delete",
            json_dumps({"id": old_val.id}),
            namespace="/userspace",
            room=old_val.user,
        )
        # await self.emit(
        #     "deployment_delete",
        #     old_val,
        #     namespace="/administrators",
        #     room=old_val.category,
        # ) # TODO
        await super().on_delete(old_val)
