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
from datetime import datetime
from typing import Optional

from api.services.error import Error
from isardvdi_common.connections.api_notifier import send_deleted_gpu_notification
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.bookings.reservables import Reservables, ReservablesProcessed
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess


# Reservable mutations bypass ApiAdmin.*_table_item, so the 5 s
# admin_table_list TTL cache must be invalidated by hand.
def _invalidate_reservable_caches(reservable_type: str) -> None:
    ApiAdmin.clear_admin_table_list_cache(reservable_type)
    if reservable_type == "gpus":
        ApiAdmin.clear_admin_table_list_cache("reservables_vgpus")


class ReservableService:

    @staticmethod
    def get_reservables() -> list[str]:
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
    def _format_item(
        item: dict, reservables: Reservables, reservable_type: str
    ) -> dict:
        # engine writes ``False`` to vgpus.changing_to_profile to clear it
        # normalize to None for the str schema.
        changing_to_profile = item.get("changing_to_profile")
        if not isinstance(changing_to_profile, str) or not changing_to_profile:
            changing_to_profile = None
        return {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "brand": item["brand"],
            "model": item["model"],
            "memory": item["memory"],
            "architecture": item["architecture"],
            "active_profile": item.get("active_profile"),
            "changing_to_profile": changing_to_profile,
            "physical_device": item.get("physical_device"),
            # GPUs only: the delegated category (None = admin-only/global) and its
            # resolved name, both computed by list_items. Without these here the
            # formatter drops them and the webapp/old-frontend never renders the
            # delegated-category label nor preselects it in the edit modal.
            "category": item.get("category"),
            "category_name": item.get("category_name"),
            # GPUs only: the auto per-card passthrough identity ("<host>n<numa>b<bus>")
            # the admin UI shows as a muted variant suggestion and adopts when
            # enabling passthrough. Dropping it here leaves the Variant column blank
            # for passthrough cards that have no explicit "~<variant>".
            "passthrough_variant": item.get("passthrough_variant"),
            "profiles_enabled": item.get("profiles_enabled", []),
            "plans": ReservableService._get_item_plans(
                reservables, reservable_type, item
            ),
            "desktops_started": item.get("desktops_started", []),
            "available_units": item.get("available_units", 0),
            "gpu_warnings": item.get("gpu_warnings", []),
        }

    @staticmethod
    def _get_item_plans(
        reservables: Reservables, reservable_type: str, item: dict
    ) -> dict:
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
    def get_reservable_detail(
        item_type: str, payload: Optional[dict] = None
    ) -> list[dict]:
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
        # A manager only sees the cards delegated to their category, so the
        # planner card selector can't enumerate another category's hardware.
        if payload is not None and payload.get("role_id") != "admin":
            items = [
                item
                for item in items
                if item.get("category") == payload.get("category_id")
            ]

        formatted_items = [
            ReservableService._format_item(item, reservables, item_type)
            for item in items
        ]
        return formatted_items

    @staticmethod
    def list_bookables(reservable_type: str) -> list[dict]:
        """Bookable reservables for the admin Bookables list, each enriched
        with the distinct categories of the GPU cards backing it.

        Replaces the generic ``/admin/items/table/reservables_vgpus`` feed so
        the response carries the computed ``categories`` natively (the table
        endpoint returns raw rows with no card join).
        """
        reservables = Reservables()
        valid_types = reservables.list_reservables()
        if reservable_type not in valid_types:
            raise Error(
                "not_found",
                f"Reservable type '{reservable_type}' not found",
                description_code="reservable_type_not_found",
            )
        return reservables.list_bookables(reservable_type)

    @staticmethod
    def list_subitems(reservable_type: str, item_id: str) -> list[dict]:
        """Return the catalog of subitems (vGPU profiles) for ``item_id``.

        v3 parity: ``GET /api/v3/admin/reservables/<type>/<id>`` returned
        ``api_ri.list_subitems(...)`` (a list of profile dicts), not the
        item itself. The webapp's "expand GPU row" child table consumes
        this list to render checkboxes and decides which are checked
        client-side by intersecting with the parent row's
        ``profiles_enabled``.
        """
        reservables = Reservables()
        valid_types = reservables.list_reservables()
        if reservable_type not in valid_types:
            raise Error(
                "not_found",
                f"Reservable type '{reservable_type}' not found",
                description_code="reservable_type_not_found",
            )
        return reservables.list_subitems(reservable_type, item_id)

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
    def get_available_reservables(payload: dict) -> dict:
        return ReservablesPlannerProccess.get_available_reservables(payload)

    @staticmethod
    def list_profiles(reservable_type: str) -> list[dict]:
        reservables = Reservables()
        return reservables.list_profiles(reservable_type)

    @staticmethod
    def add_item(reservable_type: str, data: dict) -> dict:
        reservables = Reservables()
        result = reservables.add_item(reservable_type, data)
        _invalidate_reservable_caches(reservable_type)
        return result

    @staticmethod
    def _notify_affected_users(reservable_type: str, item_id: str) -> None:
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
        reservable_type: str,
        item_id: str,
        subitem_id: str,
        enabled: bool,
        notify_user: bool = False,
    ) -> str:
        reservables = Reservables()
        if not enabled:
            # Server-side guards so a scripted/direct PUT cannot bypass the
            # UI's check/last pre-flight: refuse while an in-progress booking
            # spans now, or while a RUNNING desktop still uses the profile
            # (an admin-started desktop has no booking, so the booking guard
            # alone would let the disable strip a live domain's GPU).
            ReservablesPlannerProccess.check_subitem_current_plan(subitem_id, item_id)
            ReservablesPlannerProccess.check_subitem_running_desktops(subitem_id)
            if notify_user:
                ReservableService._notify_affected_users(reservable_type, item_id)
            ReservablesPlannerProccess.delete_subitem(
                reservable_type, item_id, subitem_id
            )
        result = reservables.enable_subitems(
            reservable_type, item_id, subitem_id, enabled
        )
        _invalidate_reservable_caches(reservable_type)
        return result["id"]

    @staticmethod
    def list_subitems_enabled(
        reservable_type: str, item_id: str, payload: Optional[dict] = None
    ) -> list[dict]:
        # A manager may list the enabled profiles only on a card delegated to
        # their category (the planner needs them to label the plan windows).
        if payload is not None:
            ReservablesPlannerProccess._assert_manager_owns_card(payload, item_id)
        reservables = Reservables()
        return reservables.list_subitems_enabled(reservable_type, item_id)

    @staticmethod
    def check_last_subitem(reservable_type: str, subitem_id: str, item_id: str) -> dict:
        ReservablesPlannerProccess.check_subitem_current_plan(subitem_id, item_id)
        return ReservablesPlannerProccess.check_subitem_desktops_and_plannings(
            reservable_type, item_id, subitem_id
        )

    @staticmethod
    def check_last_item(reservable_type: str, item_id: str) -> dict:
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
    def delete_item(
        reservable_type: str, item_id: str, notify_user: bool = False
    ) -> None:
        if notify_user:
            ReservableService._notify_affected_users(reservable_type, item_id)
        ReservablesPlannerProccess.delete_item(reservable_type, item_id)
        _invalidate_reservable_caches(reservable_type)

    @staticmethod
    def update_item(reservable_type: str, item_id: str, data: dict) -> None:
        """Update a reservable item's name and description."""
        table_map = {"gpus": "gpus", "usbs": "usbs"}
        table = table_map.get(reservable_type)
        if not table:
            raise Error("bad_request", f"Unknown reservable type: {reservable_type}")
        if ReservablesProcessed.get_item(table, item_id) is None:
            raise Error("not_found", f"Item {item_id} not found in {table}")
        # The owning category is delegated via set_item_category (one per card,
        # enforced there); keep it out of the blind update_item write. An empty
        # string clears the delegation (back to admin-only/global). (!4546)
        sentinel = object()
        category = data.pop("category", sentinel)
        if category is not sentinel:
            reservables = Reservables()
            reservables.set_item_category(reservable_type, item_id, category or None)
        update_data = {}
        if "name" in data:
            if ReservablesProcessed.name_exists_for_other(table, data["name"], item_id):
                raise Error("conflict", f"Name '{data['name']}' already exists")
            update_data["name"] = data["name"]
        if "description" in data:
            update_data["description"] = data["description"]
        ReservablesProcessed.update_item(table, item_id, update_data)
        _invalidate_reservable_caches(reservable_type)

    @staticmethod
    def list_all_plans(payload: Optional[dict] = None) -> list[dict]:
        # A manager only sees plannings on cards delegated to their category.
        return ReservablesPlannerProccess.list_all_item_plans(payload)

    @staticmethod
    def get_actual_plan(item_id: str) -> dict:
        plan = ReservablesPlannerProccess.list_item_plans(item_id)
        if not len(plan):
            return {}
        return plan[0]

    @staticmethod
    def get_item_plans(
        item_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        payload: Optional[dict] = None,
    ) -> list[dict]:
        if payload is not None:
            ReservablesPlannerProccess._assert_manager_owns_card(payload, item_id)
        return ReservablesPlannerProccess.list_item_plans(item_id, start, end)

    @staticmethod
    def add_plan(payload: dict, data: dict) -> dict:
        ReservablesPlannerProccess._assert_manager_owns_card(payload, data["item_id"])
        return ReservablesPlannerProccess.add_plan(payload, data)

    @staticmethod
    def get_plan_bookings(plan_id: str) -> list[dict]:
        return ReservablesPlannerProccess.get_plan_bookings(plan_id)

    @staticmethod
    def delete_plan(plan_id: str, payload: Optional[dict] = None) -> None:
        if payload is not None:
            ReservablesPlannerProccess._assert_manager_owns_plan(payload, plan_id)
        ReservablesPlannerProccess.delete_plan(plan_id)

    @staticmethod
    def update_plan(payload: dict, plan_id: str, start: str, end: str) -> None:
        ReservablesPlannerProccess._assert_manager_owns_plan(payload, plan_id)
        ReservablesPlannerProccess.update_plan(payload, plan_id, start, end)

    @staticmethod
    def booking_provisioning(
        payload: dict,
        subitems: dict,
        units: int,
        priority: dict,
        block_interval: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> dict:
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
    def check_integrity() -> dict:
        return ReservablesPlannerProccess.is_any_plan_item_id_overlapped()
