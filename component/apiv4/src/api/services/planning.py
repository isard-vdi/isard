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

from typing import List, Optional

from api.schemas.planning import PlanningItem
from api.services.error import Error
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess


class PlanningService:
    """Service class for handling planning operations"""

    @staticmethod
    def get_item_plannings(
        payload: dict,
        item_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[PlanningItem]:
        """
        Get plannings for a specific item

        Args:
            payload (dict): User payload from authentication
            item_id (str): The item ID to get plannings for
            start (Optional[str]): Start date filter (ISO format)
            end (Optional[str]): End date filter (ISO format)

        Returns:
            List[PlanningItem]: List of planning items
        """
        # A manager may only read plannings on a GPU card delegated to their
        # category; admins are unrestricted. Without this a manager could
        # enumerate another category's plannings by card id.
        ReservablesPlannerProccess._assert_manager_owns_card(payload, item_id)
        try:
            plannings_raw = ReservablesPlannerProccess.list_item_plans(
                item_id, start, end
            )

            plannings = []
            for plan_data in plannings_raw:
                planning_item = PlanningItem(
                    id=plan_data.get("id", ""),
                    item_id=plan_data.get("item_id", ""),
                    subitem_id=plan_data.get("subitem_id", ""),
                    start=plan_data.get("start"),
                    end=plan_data.get("end"),
                    item_type=plan_data.get("item_type"),
                    units=plan_data.get("units"),
                    priority=plan_data.get("priority"),
                )
                plannings.append(planning_item)

            return plannings
        except Error:
            raise
        except Exception as e:
            raise Error(
                "internal_server",
                f"Failed to retrieve plannings for item {item_id}: {str(e)}",
                description_code="failed_to_retrieve_plannings",
            )

    @staticmethod
    def delete_planning(payload: dict, plan_id: str) -> None:
        """
        Delete a specific planning

        Args:
            payload (dict): User payload from authentication
            plan_id (str): The planning ID to delete

        Returns:
            bool: True if successfully deleted
        """
        # A manager may only delete a planning on a card delegated to their
        # category; for any other (or missing) plan id this raises a uniform
        # not_found so plan ids cannot be enumerated across categories.
        ReservablesPlannerProccess._assert_manager_owns_plan(payload, plan_id)
        try:
            ReservablesPlannerProccess.delete_plan(plan_id)
        except Error:
            raise
        except Exception as e:
            raise Error(
                "internal_server",
                f"Failed to delete planning {plan_id}: {str(e)}",
                description_code="failed_to_delete_planning",
            )

    @staticmethod
    def create_planning(payload: dict, planning_data: dict) -> str:
        """
        Create a new planning

        Args:
            payload (dict): User payload from authentication
            planning_data (dict): Planning data to create, with dates on ISO date format

        Returns:
            str: The created planning ID
        """
        # A manager may only create a planning on a GPU card delegated to their
        # category (an unassigned/global card is admin-only); admins are
        # unrestricted.
        ReservablesPlannerProccess._assert_manager_owns_card(
            payload, planning_data["item_id"]
        )
        plan_id = ReservablesPlannerProccess.add_plan(payload, planning_data)
        return plan_id
