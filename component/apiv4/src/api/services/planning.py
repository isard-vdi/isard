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
from isardvdi_common.lib.bookings.reservables import Reservables as ReservablesProccess
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess


class PlanningService:
    """Service class for handling planning operations"""

    @staticmethod
    def get_item_plannings(
        item_id: str, start: Optional[str] = None, end: Optional[str] = None
    ) -> List[PlanningItem]:
        """
        Get plannings for a specific item

        Args:
            item_id (str): The item ID to get plannings for
            start (Optional[str]): Start date filter (ISO format)
            end (Optional[str]): End date filter (ISO format)

        Returns:
            List[PlanningItem]: List of planning items
        """
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
    def delete_planning(plan_id: str) -> None:
        """
        Delete a specific planning

        Args:
            plan_id (str): The planning ID to delete

        Returns:
            bool: True if successfully deleted
        """
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
        if not hasattr(ReservablesPlannerProccess, "reservables"):
            ReservablesPlannerProccess.reservables = ReservablesProccess()

        plan_id = ReservablesPlannerProccess.add_plan(payload, planning_data)
        return plan_id
