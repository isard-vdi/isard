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


from datetime import datetime

from .base import BaseHandler, json_dumps


class ResourcePlannerHandler(BaseHandler):
    def _parse_start_end_data(self, plan):
        """
        Parse the start and end data from the plan.
        """
        start = plan.start
        end = plan.end
        if isinstance(start, datetime):
            start = start.strftime("%Y-%m-%dT%H:%M%z")
        if isinstance(end, datetime):
            end = end.strftime("%Y-%m-%dT%H:%M%z")

        return plan.model_copy(update={"start": start, "end": end})

    async def on_insert(self, new_val):
        plan = self._parse_start_end_data(new_val)
        await self.emit(
            "plan_add",
            json_dumps(plan),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await super().on_insert(plan)

    async def on_update(self, old_val, new_val):
        plan = self._parse_start_end_data(new_val)
        await self.emit(
            "plan_update",
            json_dumps(plan),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await super().on_update(old_val, plan)

    async def on_delete(self, old_val):
        plan = self._parse_start_end_data(old_val)
        await self.emit(
            "plan_delete",
            json_dumps(plan),
            namespace="/userspace",
            room=old_val.user_id,
        )
        await super().on_delete(old_val)
