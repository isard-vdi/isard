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


import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed,
)
from isardvdi_common.models.user import User
from rethinkdb import r


class DeploymentUsers(RethinkSharedConnection):

    _rdb_table = "deployments"

    @classmethod
    def get_users_info(cls, deployment_id):
        """
        Get a list of users who have access to the deployment and the total amount of users.
        This includes their name, their last access and the amount of started desktops.
        """
        deployment_users = cls.get_users(deployment_id)

        if not deployment_users:
            return []

        with cls._rdb_context():
            users_data = list(
                r.table("users")
                .get_all(r.args(deployment_users))
                .pluck("id", "name", "username", "photo")
                .run(cls._rdb_connection)
            )

        user_map = {
            user["id"]: {
                "id": user["id"],
                "name": user["name"],
                "username": user["username"],
                "photo": user.get("photo"),
                "desktops_statuses": [],
                "visible": False,
                "last_access": None,
            }
            for user in users_data
        }
        grouped_desktops = (
            DeploymentDesktopsProcessed.get_deployment_desktops_grouped_by_user_status(
                deployment_id
            )
        )
        # Match each user with its desktops
        for user_desktops in grouped_desktops:
            user_id = user_desktops["user"]
            if user_id in user_map:
                user_map[user_id]["desktops_statuses"] = user_desktops["statuses"]
                user_map[user_id]["visible"] = user_desktops["visible"]
                user_map[user_id]["last_access"] = user_desktops["last_access"]

        return list(user_map.values())

    @classmethod
    def get_users(cls, deployment_id):
        with cls._rdb_context():
            deployment = (
                r.table(cls._rdb_table)
                .get(deployment_id)
                .pluck("allowed")
                .run(cls._rdb_connection)
            )

        allowed = deployment.get("allowed", {})
        user_ids = (
            allowed.get("users") if isinstance(allowed.get("users"), list) else []
        )
        group_ids = (
            allowed.get("groups") if isinstance(allowed.get("groups"), list) else []
        )

        with cls._rdb_context():
            groups_users_ids = list(
                r.table("users")
                .get_all(r.args(group_ids), index="group")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

        return user_ids + groups_users_ids

    @classmethod
    def get_selected_users(
        cls,
        payload,
        selected,
        desktop_name=None,
        deployment_id=None,
        existing_desktops_error=False,
        include_existing_desktops=False,
        add_payload_user=True,
    ):
        """Check who has to be created"""
        users = []

        group_users = []

        secondary_groups_users = []
        if selected["groups"] is not False:
            query_group_users = (
                r.table("users")
                .get_all(r.args(selected["groups"]), index="group")
                .filter(lambda user: user["active"].eq(True))
                .pluck("id", "username", "category", "group")
            )
            if payload["role_id"] != "admin":
                query_group_users.filter({"category": payload["category_id"]})
            with cls._rdb_context():
                group_users = list(query_group_users.run(cls._rdb_connection))

            with cls._rdb_context():
                secondary_groups_users = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="secondary_groups")
                    .filter(lambda user: user["active"].eq(True))
                    .pluck("id", "username", "category", "group")
                    .run(cls._rdb_connection)
                )

        user_users = []
        if selected.get("users") is not False and selected.get("users"):
            with cls._rdb_context():
                query_user_users = (
                    r.table("users")
                    .get_all(r.args(selected["users"]), index="id")
                    .filter(lambda user: user["active"].eq(True))
                    .pluck("id", "username", "category", "group")
                )
            if payload["role_id"] != "admin":
                query_user_users.filter({"category": payload["category_id"]})
            with cls._rdb_context():
                user_users = list(query_user_users.run(cls._rdb_connection))

        users = group_users + user_users + secondary_groups_users
        # Remove duplicate user dicts in list
        users = list({u["id"]: u for u in users}.values())

        """ DOES THE USERS ALREADY HAVE A DESKTOP WITH THIS NAME? """
        users_ids = [u["id"] for u in users]

        filter_dict = {"kind": "desktop"}
        if deployment_id:
            filter_dict["tag"] = deployment_id
        if desktop_name:
            filter_dict["name"] = desktop_name

        with cls._rdb_context():
            existing_desktops = [
                u["user"]
                for u in list(
                    r.table("domains")
                    .get_all(r.args(users_ids), index="user")
                    .filter(filter_dict)
                    .pluck("id", "user", "username")
                    .run(cls._rdb_connection)
                )
            ]
        if len(existing_desktops):
            if existing_desktops_error:
                raise Error(
                    "conflict",
                    "This users already have a desktop with this name: "
                    + str(existing_desktops),
                    description_code="new_desktop_name_exists",
                    params={"users": existing_desktops, "name": desktop_name},
                )
            elif not include_existing_desktops:
                users = [u for u in users if u["id"] not in existing_desktops]
        return users

    @classmethod
    def edit_deployment_users(cls, payload, deployment_id, allowed):
        deployment = Caches.get_document("deployments", deployment_id)
        if not deployment:
            raise Error(
                "not_found",
                "Not found deployment id to edit its users: " + str(deployment_id),
                description_code="not_found",
            )
        with cls._rdb_context():
            deployment = (
                r.table("deployments").get(deployment_id).run(cls._rdb_connection)
            )

        # Local import to avoid the deployments <-> deployment_users
        # circular module dependency.
        from isardvdi_common.lib.deployments.deployments import (  # noqa: E501
            DeploymentsProcessed,
        )

        deployment_booking = DeploymentsProcessed._parse_booking(deployment_id)
        if deployment_booking.get("next_booking_end"):
            raise Error(
                "precondition_required",
                "Can't edit a deployment with a scheduled booking",
                traceback.format_exc(),
                "cant_edit_booked_deployment",
            )
        with cls._rdb_context():
            r.table("deployments").get(deployment_id).update(
                {
                    "allowed": allowed,
                }
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("deployments", deployment_id)

        old_users = cls.get_selected_users(
            payload,
            deployment.get("allowed"),
            deployment_id=deployment_id,
            existing_desktops_error=False,
            include_existing_desktops=True,
        )
        new_users = cls.get_selected_users(
            payload,
            allowed,
            deployment_id=deployment_id,
            existing_desktops_error=False,
            include_existing_desktops=True,
        )

        with cls._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(
                    r.args(
                        [
                            ["desktop", user["id"], deployment_id]
                            for user in old_users
                            if user not in new_users
                        ]
                    ),
                    index="kind_user_tag",
                )
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )
        if len(desktops_ids):
            DesktopEvents.deployment_delete_desktops(
                agent_id=payload["user_id"],
                desktops_ids=desktops_ids,
                permanent=True,
            )
        # cls.recreate(payload, deployment_id)
