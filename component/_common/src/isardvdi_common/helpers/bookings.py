#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Pau Abril Iranzo, Miriam Melina Gamboa Valdez
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


import logging as log
import traceback
from datetime import datetime

import pytz
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.scheduler import Scheduler
from rethinkdb import r


class Bookings(RethinkSharedConnection):

    @classmethod
    def delete_item_bookings(cls, item_type, item_id):
        with cls._rdb_context():
            if not Helpers._check(
                r.table("bookings")
                .get_all([item_type, item_id], index="item_type-id")
                .delete()
                .run(cls._rdb_connection),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Unable to delete item bookings",
                    traceback.format_stack(),
                )
        Scheduler.bookings_remove_scheduled_jobs(item_id)

    @classmethod
    def is_future(cls, event):
        return True if event["start"] > datetime.now(pytz.utc) else False

    @classmethod
    def _get_reservables(cls, item_type, item_id):
        if item_type == "desktop":
            with cls._rdb_context():
                data = r.table("domains").get(item_id).run(cls._rdb_connection)
            if not data:
                raise Error(
                    "not_found",
                    f"Desktop {item_id} not found",
                    description_code="not_found",
                )
            units = 1
            item_name = data["name"]

            if not data["create_dict"].get("reservables") or not any(
                list(data["create_dict"]["reservables"].values())
            ):
                raise Error(
                    "precondition_required",
                    "Item has no reservables",
                    description_code="no_reservables",
                )
            data = data["create_dict"]["reservables"]
            data_without_falses = {k: v for k, v in data.items() if v}
            return (data_without_falses, units, item_name)

        elif item_type == "deployment":
            with cls._rdb_context():
                deployment = (
                    r.table("deployments").get(item_id).run(cls._rdb_connection)
                )
            if not deployment:
                raise Error(
                    "not_found",
                    "Deployment id not found",
                    description_code="not_found",
                )

            # Filter out None values
            valid_vgpus = [
                tuple(item["reservables"]["vgpus"])
                for item in deployment["create_dict"]
                if item["reservables"]["vgpus"] is not None
            ]

            # Check that all the gpus are the same
            if valid_vgpus and any(v != valid_vgpus[0] for v in valid_vgpus):
                raise Error(
                    "precondition_required",
                    "Deployment reservables are not equal across all desktops.",
                    description_code="deployment_reservables_not_equal",
                )

            # Number of units that will be reserved
            payload = Helpers.gen_payload_from_user(deployment.get("user"))

            # TODO: Imported here to avoid circular imports
            from isardvdi_common.lib.deployments.deployment_users import DeploymentUsers

            users_amount = len(
                DeploymentUsers.get_selected_users(
                    payload, deployment.get("allowed"), ""
                )
            )
            units = len(valid_vgpus * users_amount)
            common_vgpus = list(valid_vgpus[0]) if valid_vgpus else None

            item_name = deployment["name"]

            # TODO: Should return all of the reservables and not only vgpus
            return (
                {
                    "vgpus": common_vgpus,
                },
                units,
                item_name,
            )
        else:
            raise Error(
                "not_found",
                "Item type " + str(item_type) + " not found",
                description_code="not_found",
            )
