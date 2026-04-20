#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

import logging as log

from api.services.error import Error
from isardvdi_common.connections.api_notifier import send_deleted_gpu_notification
from isardvdi_common.lib.bookings.reservables import Reservables
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess


class ReservableService:

    @staticmethod
    def get_reservables():
        """
        Get a list of all reservable types
        """
        try:
            reservables = Reservables()
            return reservables.list_reservables()
        except Exception as e:
            raise Error(
                "internal_server",
                f"Failed to retrieve reservables: {str(e)}",
                description_code="failed_to_retrieve_reservables",
            )

    @staticmethod
    def _format_item(item, reservables, reservable_type):
        return {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "brand": item["brand"],
            "model": item["model"],
            "memory": item["memory"],
            "architecture": item["architecture"],
            "active_profile": item.get("active_profile"),
            "changing_to_profile": item.get("changing_to_profile"),
            "physical_device": item.get("physical_device"),
            "profiles_enabled": item.get("profiles_enabled", []),
            "plans": ReservableService._get_item_plans(
                reservables, reservable_type, item
            ),
        }

    @staticmethod
    def _get_item_plans(reservables, reservable_type, item):
        """
        Calculate the plans data for a reservable

        Args:
            reservables: Reservables instance
            reservable_type: Type of reservable (e.g., "gpus")
            item: The item data

        Returns:
            dict: Plans data with current count, active status, and profile
        """
        total_plans = ReservablesPlannerProccess().list_item_plans(item["id"])
        profile = total_plans[0]["subitem_id"] if total_plans else None

        if profile:
            try:
                profile_data = reservables.get_subitem(
                    reservable_type, item["id"], profile
                )
                profile = profile_data["profile"]
            except Exception:
                log.exception(
                    "Failed to load reservable subitem %s/%s/%s",
                    reservable_type,
                    item["id"],
                    profile,
                )
                profile = None

        return {
            "current": len(total_plans),
            "active": profile == item.get("active_profile"),
            "profile": profile,
        }

    @staticmethod
    def get_reservable_detail(item_type: str):
        """
        Get detailed information for a specific reservable type

        Args:
            item_id (str): The reservable type ID (e.g., "gpus", "usbs")

        Returns:
            List[dict]: List of reservable items for the specified type
        """
        reservables = Reservables()

        valid_types = reservables.list_reservables()
        if item_type not in valid_types:
            raise Error(
                "not_found",
                f"Reservable type '{item_type}' not found",
                description_code="reservable_type_not_found",
            )
        items = reservables.list_items(item_type)

        formatted_items = [
            ReservableService._format_item(item, reservables, item_type)
            for item in items
        ]
        return formatted_items

    @staticmethod
    def get_reservable_item(reservable_type: str, item_id: str):
        """
        Get detailed information for a specific reservable item

        Args:
            reservable_type (str): The reservable type (e.g., "gpus")
            item_id (str): The specific item ID

        Returns:
            dict: Detailed information for the specific reservable item
        """
        try:
            reservables = Reservables()
            valid_types = reservables.list_reservables()
            if reservable_type not in valid_types:
                raise Error(
                    "not_found",
                    f"Reservable type '{reservable_type}' not found",
                    description_code="reservable_type_not_found",
                )

            items = reservables.list_items(reservable_type)
            target_item = next((i for i in items if i.get("id") == item_id), None)

            if not target_item:
                raise Error(
                    "not_found",
                    f"Reservable item '{item_id}' not found in type '{reservable_type}'",
                    description_code="reservable_item_not_found",
                )

            formatted_item = ReservableService._format_item(
                target_item, reservables, reservable_type
            )

            return formatted_item

        except Error:
            raise
        except Exception as e:
            raise Error(
                "internal_server",
                f"Failed to retrieve reservable item '{item_id}' of type '{reservable_type}': {str(e)}",
                description_code="failed_to_retrieve_reservable_item",
            )

    @staticmethod
    def reservable_item_exists(item_id: str) -> bool:
        """
        Check if a reservable item exists across all types
        """
        try:
            reservables = Reservables()
            for reservable_type in reservables.list_reservables():
                items = reservables.list_items(reservable_type)
                if any(item.get("id") == item_id for item in items):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_available_reservables(payload):
        return ReservablesPlannerProccess.get_available_reservables(payload)

    @staticmethod
    def list_profiles(reservable_type):
        reservables = Reservables()
        return reservables.list_profiles(reservable_type)

    @staticmethod
    def add_item(reservable_type, data):
        reservables = Reservables()
        return reservables.add_item(reservable_type, data)

    @staticmethod
    def _notify_affected_users(reservable_type, item_id):
        """Fan out a ``deleted-gpu`` email to every user whose desktops,
        deployments or bookings reference the reservable ``item_id``.

        Mirrors v3 ``api_v3_reservable_delete_gpu`` / ``_enable_gpu``
        notify_user branch (api/views/bookings/ReservablesView.py). The
        notifier service handles the template rendering + SMTP send; the
        API just gathers the affected users from the common helpers.
        """
        reservables = Reservables()
        subitems = [
            s["id"] for s in reservables.list_subitems_enabled(reservable_type, item_id)
        ]
        users_items = []
        for subitem in subitems:
            ReservablesPlannerProccess.get_item_users(
                reservable_type, item_id, users_items, subitem
            )
        for user_items in users_items:
            try:
                send_deleted_gpu_notification(
                    user_id=user_items["user_id"],
                    bookings=[
                        {
                            "start": str(booking["start"]),
                            "end": str(booking["end"]),
                            "title": str(booking["title"]),
                        }
                        for booking in user_items.get("bookings", [])
                    ],
                    desktops=[
                        {"name": str(desktop["name"])}
                        for desktop in user_items.get("desktops", [])
                    ],
                    deployments=[
                        {"name": str(deployment["tag_name"])}
                        for deployment in user_items.get("deployments", [])
                    ],
                )
            except Exception:
                log.exception(
                    "Failed to send deleted-gpu notification to user %s",
                    user_items.get("user_id"),
                )

    @staticmethod
    def enable_subitem(
        reservable_type, item_id, subitem_id, enabled, notify_user=False
    ):
        reservables = Reservables()
        if not enabled:
            if notify_user:
                ReservableService._notify_affected_users(reservable_type, item_id)
            ReservablesPlannerProccess.delete_subitem(
                reservable_type, item_id, subitem_id
            )
        result = reservables.enable_subitems(
            reservable_type, item_id, subitem_id, enabled
        )
        return result["id"]

    @staticmethod
    def list_subitems_enabled(reservable_type, item_id):
        reservables = Reservables()
        return reservables.list_subitems_enabled(reservable_type, item_id)

    @staticmethod
    def check_last_subitem(reservable_type, subitem_id, item_id):
        ReservablesPlannerProccess.check_subitem_current_plan(subitem_id, item_id)
        return ReservablesPlannerProccess.check_subitem_desktops_and_plannings(
            reservable_type, item_id, subitem_id
        )

    @staticmethod
    def check_last_item(reservable_type, item_id):
        reservables = Reservables()
        data = {
            "last": [],
            "desktops": [],
            "plans": [],
            "bookings": [],
            "deployments": [],
        }
        profiles = reservables.list_subitems_enabled(reservable_type, item_id)
        for profile in profiles:
            ReservablesPlannerProccess.check_subitem_current_plan(
                profile["id"], item_id
            )
            subitem_data = (
                ReservablesPlannerProccess.check_subitem_desktops_and_plannings(
                    reservable_type, item_id, profile["id"]
                )
            )
            data["last"].extend(subitem_data.get("last", []))
            if True in subitem_data.get("last"):
                data["desktops"].extend(subitem_data.get("desktops", []))
                data["plans"].extend(subitem_data.get("plans", []))
                data["bookings"].extend(subitem_data.get("bookings", []))
                data["deployments"].extend(subitem_data.get("deployments", []))
        return data

    @staticmethod
    def delete_item(reservable_type, item_id, notify_user=False):
        if notify_user:
            ReservableService._notify_affected_users(reservable_type, item_id)
        ReservablesPlannerProccess.delete_item(reservable_type, item_id)

    @staticmethod
    def update_item(reservable_type, item_id, data):
        """Update a reservable item's name and description."""
        from rethinkdb import r

        table_map = {"gpus": "gpus", "usbs": "usbs"}
        table = table_map.get(reservable_type)
        if not table:
            raise Error("bad_request", f"Unknown reservable type: {reservable_type}")
        with ReservablesPlannerProccess._rdb_context():
            item = (
                r.table(table)
                .get(item_id)
                .run(ReservablesPlannerProccess._rdb_connection)
            )
        if not item:
            raise Error("not_found", f"Item {item_id} not found in {table}")
        update_data = {}
        if "name" in data:
            # Check duplicate name
            with ReservablesPlannerProccess._rdb_context():
                existing = list(
                    r.table(table)
                    .filter(
                        lambda g: (g["name"] == data["name"]) & (g["id"] != item_id)
                    )
                    .run(ReservablesPlannerProccess._rdb_connection)
                )
            if existing:
                raise Error("conflict", f"Name '{data['name']}' already exists")
            update_data["name"] = data["name"]
        if "description" in data:
            update_data["description"] = data["description"]
        if update_data:
            with ReservablesPlannerProccess._rdb_context():
                r.table(table).get(item_id).update(update_data).run(
                    ReservablesPlannerProccess._rdb_connection
                )

    @staticmethod
    def list_all_plans():
        return ReservablesPlannerProccess.list_all_item_plans()

    @staticmethod
    def get_actual_plan(item_id):
        plan = ReservablesPlannerProccess.list_item_plans(item_id)
        if not len(plan):
            return {}
        return plan[0]

    @staticmethod
    def get_item_plans(item_id):
        return ReservablesPlannerProccess.list_item_plans(item_id)

    @staticmethod
    def add_plan(payload, data):
        return ReservablesPlannerProccess.add_plan(payload, data)

    @staticmethod
    def get_plan_bookings(plan_id):
        return ReservablesPlannerProccess.get_plan_bookings(plan_id)

    @staticmethod
    def delete_plan(plan_id):
        ReservablesPlannerProccess.delete_plan(plan_id)

    @staticmethod
    def update_plan(payload, plan_id, start, end):
        ReservablesPlannerProccess.update_plan(payload, plan_id, start, end)

    @staticmethod
    def booking_provisioning(
        payload, subitems, units, priority, block_interval, start=None, end=None
    ):
        from isardvdi_common.lib.bookings.reservables_planner_compute import (
            ReservablesPlannerCompute,
        )

        return ReservablesPlannerCompute.booking_provisioning(
            payload=payload,
            item_type=None,
            item_id=None,
            subitems=subitems,
            units=units,
            priority=priority,
            fromDate=start,
            toDate=end,
        )

    @staticmethod
    def check_integrity():
        return ReservablesPlannerProccess.is_any_plan_item_id_overlapped()
