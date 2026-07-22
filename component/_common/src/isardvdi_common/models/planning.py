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

from datetime import datetime
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel, Field
from rethinkdb import r


class ResourcePlannerModel(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    item_id: str
    item_type: str
    subitem_id: str
    start: datetime
    end: datetime
    user_id: str
    event_type: str
    units: int


class ResourcePlanner(RethinkCustomBase):
    _rdb_table = "resource_planner"

    @classmethod
    def insert_plan(cls, plan_data):
        with cls._rdb_context():
            result = r.table(cls._rdb_table).insert(plan_data).run(cls._rdb_connection)
        return result.get("inserted", 0) > 0

    @classmethod
    def get_plans(cls, item_id, start, end):
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(item_id, index="item_id")
                .filter(r.row["start"] <= end)
                .filter(r.row["end"] >= start)
                .run(cls._rdb_connection)
            )

    @classmethod
    def delete_plan_by_id(cls, plan_id):
        """
        Delete a plan by its ID from the resource_planner table.

        Args:
            plan_id (str): The ID of the plan to delete

        Returns:
            dict: Result of the delete operation
        """
        with cls._rdb_context():
            return (
                r.table(cls._rdb_table).get(plan_id).delete().run(cls._rdb_connection)
            )

    @classmethod
    def delete_bookings_by_plan_id(cls, plan_id):
        """
        Delete bookings associated with a specific plan ID.

        Args:
            plan_id (str): The ID of the plan whose bookings should be deleted

        Returns:
            dict: Result of the delete operation
        """
        with cls._rdb_context():
            return (
                r.table("bookings")
                .filter(
                    r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
                )
                .delete(return_changes=True)
                .run(cls._rdb_connection)
            )
