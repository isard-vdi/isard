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
from datetime import datetime

from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.models.deployment import Deployment
from isardvdi_common.models.domain import Domain

from .base import BaseHandler, json_dumps


class BookingsHandler(BaseHandler):

    def _prepare_booking(self, booking):
        """
        Prepare booking data for emission: format dates, add editable and
        event_type flags.
        """
        start = booking.start
        end = booking.end
        if isinstance(start, datetime):
            start = start.strftime("%Y-%m-%dT%H:%M%z")
        if isinstance(end, datetime):
            end = end.strftime("%Y-%m-%dT%H:%M%z")

        prepared = booking.model_copy(update={"start": start, "end": end})
        prepared.additional_properties = {
            **(booking.additional_properties or {}),
            "event_type": "event",
            "editable": True,
        }
        return prepared

    async def on_insert(self, new_val):
        booking = self._prepare_booking(
            new_val
        )  # TODO: Check the added booking is editable or not
        await self.emit(
            "booking_add",
            json_dumps(booking),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await self.emit(
            "bookingitem_add",
            json_dumps(booking),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await self.send_booking_item_event(booking)

    async def on_update(self, old_val, new_val):
        booking = self._prepare_booking(
            new_val
        )  # TODO: Check the added booking is editable or not
        await self.emit(
            "booking_update",
            json_dumps(booking),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await self.emit(
            "bookingitem_update",
            json_dumps(booking),
            namespace="/userspace",
            room=new_val.user_id,
        )
        await self.send_booking_item_event(booking)

    async def on_delete(self, old_val):
        booking = self._prepare_booking(
            old_val
        )  # TODO: Check the added booking is editable or not
        await self.emit(
            "booking_delete",
            json_dumps({"id": old_val.id}),
            namespace="/userspace",
            room=old_val.user_id,
        )
        await self.emit(
            "bookingitem_delete",
            json_dumps(booking),
            namespace="/userspace",
            room=old_val.user_id,
        )
        await self.send_booking_item_event(booking)

    async def send_booking_item_event(self, booking):
        """
        Emit an event for booking item changes to the related item.
        :param booking: The booking data.
        """

        if booking.item_type == "deployment":
            deployment = await asyncio.to_thread(
                DeploymentsProcessed.get_deployment, booking.item_id
            )
            await self.emit(
                "deployment_update",
                json_dumps(deployment),
                namespace="/userspace",
                room=booking.user_id,
            )
            for desktop in deployment.get("desktops", []):
                await self.emit(
                    "desktop_update",
                    json_dumps(desktop),
                    namespace="/userspace",
                    room=desktop["user"],
                )
        elif booking.item_type == "desktop":
            # ``Domain.get`` reads the row and ``_parse_desktop`` enriches via
            # ``Caches.get_document`` (DB on cache miss). Bundle both in a
            # single ``to_thread`` so the loop only pays one thread hop.
            desktop = await asyncio.to_thread(
                lambda: DesktopsProcessed._parse_desktop(Domain.get(booking.item_id))
            )
            await self.emit(
                "desktop_update",
                json_dumps(desktop),
                namespace="/userspace",
                room=booking.user_id,
            )
