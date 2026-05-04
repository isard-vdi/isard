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


class VgpusHandler(BaseHandler):

    async def on_insert(self, new_val):
        await self._emit_vgpu_data(new_val)

    async def on_update(self, old_val, new_val):
        await self._emit_vgpu_data(new_val)

    async def _emit_vgpu_data(self, val):
        props = val.additional_properties or {}
        active_profile = props.get("vgpu_profile")
        desktops_started = []
        available_units = 0
        if active_profile and active_profile in props.get("mdevs", {}):
            active_pool = props["mdevs"][active_profile]
            available_units = len(active_pool)
            for mdev_data in active_pool.values():
                if (
                    mdev_data.get("domain_started")
                    and mdev_data["domain_started"] is not False
                ):
                    desktops_started.append(mdev_data["domain_started"])
        await self.emit(
            "vgpu_data",
            json_dumps(
                {
                    "id": props.get("id"),
                    "vgpu_profile": active_profile,
                    "changing_to_profile": props.get("changing_to_profile", False),
                    "desktops_started": desktops_started,
                    # Pool size of the new active profile. Without this, the
                    # webapp's "started/total" progress bar keeps the previous
                    # profile's max as the denominator after a profile change.
                    "available_units": available_units,
                }
            ),
            "/administrators",
            "admins",
        )
