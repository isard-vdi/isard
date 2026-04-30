#
#   Copyright © 2025 Pau Abril Iranzo
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


from datetime import datetime, timezone
from typing import Literal

from api.schemas.bookings import CreateBookingEventRequest
from isardvdi_common.lib.bookings.bookings import BookingsProcessed as CommonBookings
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess
from isardvdi_common.lib.domains.desktops.desktops import (
    DesktopsProcessed as CommonDesktop,
)
from pydantic import AwareDatetime


class BookingsService:

    @staticmethod
    def get_user_bookings(
        start_date: AwareDatetime,
        end_date: AwareDatetime,
        payload: dict,
    ) -> list[dict]:
        # TODO: update code in isardvdi_common to recieve datetime objects directly, instead of recieving strings and parsing them
        start_date = start_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z")
        end_date = end_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z")

        return CommonBookings.get_user_bookings(
            start_date,
            end_date,
            payload["user_id"],
        )

    @staticmethod
    def get_item_bookings(
        payload: dict,
        start_date: AwareDatetime,
        end_date: AwareDatetime,
        item_type: Literal["desktop", "deployment"],
        item_id: str,
        return_type: Literal["all", "event", "availability"] = "all",
    ) -> list[dict] | dict:
        # TODO: update code in isardvdi_common to recieve datetime objects directly, instead of recieving strings and parsing them
        start_date = start_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z")
        end_date = end_date.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M%z")

        return CommonBookings.get_item_bookings(
            payload=payload,
            fromDate=start_date,
            toDate=end_date,
            item_type=item_type,
            item_id=item_id,
            returnType=return_type,
        )

    @staticmethod
    def create_booking_event(
        payload: dict, new_event: CreateBookingEventRequest
    ) -> dict:
        # TODO: Evaluate if perhaps the desktop could also be started
        return CommonBookings.add(
            payload=payload,
            start=new_event.start.strftime("%Y-%m-%dT%H:%M%z"),
            end=new_event.end.strftime("%Y-%m-%dT%H:%M%z"),
            item_type=new_event.item_type,
            item_id=new_event.item_id,
            title=new_event.title,
            now=new_event.now,
        )

    @staticmethod
    def update_booking_event(
        payload: dict, booking_id: str, title: str, start: str, end: str
    ) -> dict:
        """Edit an existing booking event.

        Mirrors v3 ``BookingView.py:148-160``: forwards the new
        title/start/end to ``CommonBookings.update`` which validates
        the new window against existing planner state and the
        owner's quota.
        """
        return CommonBookings.update(
            booking_id=booking_id,
            payload=payload,
            title=title,
            start=start,
            end=end,
        )

    @staticmethod
    def delete_booking_event(booking_id: str) -> None:
        """Delete an existing booking event.

        Mirrors v3 ``BookingView.py:135-147``: delegates to
        ``CommonBookings.delete`` which guards against deleting an
        in-progress booking when the underlying desktop/deployment
        is still running.
        """
        return CommonBookings.delete(booking_id=booking_id)

    @staticmethod
    def get_user_priority_for_desktop(payload: dict, desktop_id: str) -> dict:
        """Compute the booking priority of ``payload`` for a desktop.

        Mirrors v3 ``BookingView.py:42-55``: combines the result of
        ``CommonBookings.get_user_priority(payload, item_type,
        item_id)`` with the desktop name. The route name fixes the
        item_type to ``desktop``; deployment-priority lookups go
        through a separate endpoint.
        """
        priority = CommonBookings.get_user_priority(payload, "desktop", desktop_id)
        try:
            desktop = CommonDesktop.get_desktop(desktop_id)
        except Exception:
            desktop = {}
        return {**priority, "name": desktop.get("name", "")}

    @staticmethod
    def get_max_booking_date(payload: dict, desktop_id: str) -> dict:
        return CommonDesktop.check_max_booking_date(
            payload=payload,
            desktop_id=desktop_id,
        )

    @staticmethod
    def get_all_bookings() -> list[dict]:
        return CommonBookings.get_all()

    @staticmethod
    def get_users_priorities(rule_id: str) -> list[dict]:
        return CommonBookings.get_users_priorities(rule_id)

    @staticmethod
    def delete_users_priority(priority_id: str) -> None:
        CommonBookings.delete_users_priority(priority_id)

    @staticmethod
    def list_priority_rules() -> list[dict]:
        return CommonBookings.list_priority_rules()

    @staticmethod
    def get_item_availability(payload: dict, item_type: str, item_id: str) -> dict:
        return ReservablesPlannerProccess.get_item_availability(
            payload, item_type, item_id, None, None
        )

    @staticmethod
    def get_gpu_bookings_forecast() -> dict:
        return CommonBookings.get_booking_profile_count_within_one_hour()

    @staticmethod
    def empty_planning(plan_id: str) -> None:
        CommonBookings.empty_planning(plan_id)

    @staticmethod
    def get_booking_plans(booking_id: str) -> list[dict]:
        return CommonBookings.get_booking_plans(booking_id)

    @staticmethod
    def get_available_reservables(payload: dict) -> list[dict]:
        return ReservablesPlannerProccess.get_available_reservables(payload)
