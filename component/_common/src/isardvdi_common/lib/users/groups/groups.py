#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer
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


import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r

from ....helpers.caches import Caches
from ....helpers.desktop_events import DesktopEvents
from ....helpers.helpers import Helpers
from ....models.group import Group


class GroupsProcessed(RethinkSharedConnection):

    _rdb_table = "groups"

    @classmethod
    def get_with_category(cls, category_id: str | None) -> list:
        """
        Get all groups with their categories.

        Returns:
            list: A list of dictionaries containing group information.
        """
        query = r.table(cls._rdb_table)

        if category_id:
            query = query.get_all(category_id, index="parent_category")

        query = query.merge(
            {
                "category_name": r.table("categories").get(r.row["parent_category"])[
                    "name"
                ],
                "category_id": r.row["parent_category"],
            }
        ).pluck("id", "name", "category_id", "category_name")

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def code_search(cls, code: str):
        """
        Search for a group by a user's code across roles: manager, advanced, user.
        Returns role, category, and group ID if found.
        Raises an error if not found.
        """
        roles = ["manager", "advanced", "user"]

        for role in roles:
            with cls._rdb_context():
                cursor = (
                    r.table(cls._rdb_table)
                    .filter({f"enrollment": {role: code}})
                    .pluck("id", "parent_category", "code")
                    .limit(1)
                    .run(cls._rdb_connection)
                )
            group = next(cursor, None)
            if group:
                return {
                    "role_id": role,
                    "category_id": group["parent_category"],
                    "group_id": group["id"],
                }

        raise Error(
            "not_found",
            f"Group with code {code} not found.",
            description_code="not_found",
        )

    @classmethod
    def group_get_full_data(cls, group_id):
        """_From api/libv2/api_users.py ApiUsers.group_get_full_data()_"""
        with cls._rdb_context():
            exists = r.table("groups").get(group_id).run(cls._rdb_connection)
        if not exists:
            raise Error(
                "not_found",
                "Not found group_id " + group_id,
                traceback.format_exc(),
                description_code="group_not_found",
            )
        with cls._rdb_context():
            group = (
                r.table("groups")
                .get(group_id)
                .merge(
                    lambda d: {
                        "linked_groups_data": r.table("groups")
                        .get_all(r.args(d["linked_groups"].default([])))
                        .pluck("id", "name")
                        .coerce_to("array")
                    }
                )
                .run(cls._rdb_connection)
            )
        return group

    @classmethod
    def admin_get_groups(cls):
        """_From api/libv2/api_users.py ApiUsers.GroupsGet()_"""
        with cls._rdb_context():
            return list(
                r.table("groups")
                .order_by("name")
                .merge(
                    lambda group: {
                        "linked_groups_data": r.table("groups")
                        .get_all(r.args(group["linked_groups"].default([])))
                        .pluck("id", "name")
                        .coerce_to("array"),
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def delete_group(cls, group_id, agent_id):
        """_From api/libv2/api_users.py ApiUsers.GroupDelete()_"""
        # Check the group exists
        if not Group.exists(group_id):
            raise Error(
                "not_found",
                "Not found group_id " + group_id,
                traceback.format_exc(),
                description_code="group_not_found",
            )

        with cls._rdb_context():
            group_media_ids = list(
                r.table("media")
                .get_all(group_id, index="group")["id"]
                .run(cls._rdb_connection)
            )
        if group_media_ids:
            Helpers.change_owner_medias(
                group_media_ids,
                Helpers.get_new_user_data("local-default-admin-admin"),
            )

        DesktopEvents.group_delete(agent_id, group_id)

    @classmethod
    def update_group_quota(
        cls,
        group,
        quota,
        propagate,
        role=False,
        user_role="manager",
    ):
        """_From api/libv2/api_users.py ApiUsers.UpdateGroupQuota()_"""
        category = cls.CategoryGet(group["parent_category"], True)
        # Managers can't update a group quota with a higher value than its category quota
        if user_role == "manager":
            if category["quota"] != False:
                for k, v in category["quota"].items():
                    if quota and quota.get(k) and v < quota[k]:
                        raise Error(
                            "precondition_required",
                            "Can't update "
                            + group["name"]
                            + " "
                            + k
                            + " quota value with a higher value than its category quota",
                            traceback.format_exc(),
                        )

        # Can't update a group quota with a higher value than its category limit
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if quota and quota.get(k) and v < quota[k]:
                    raise Error(
                        "precondition_required",
                        "Can't update "
                        + group["name"]
                        + " "
                        + k
                        + " quota value with a higher value than its category limit",
                        traceback.format_exc(),
                    )

        if not role:
            with cls._rdb_context():
                # TODO(move-users-to-common): pydantic validation
                r.table("groups").get(group["id"]).update({"quota": quota}).run(
                    cls._rdb_connection
                )

        if propagate or role:
            query = r.table("users").get_all(group["id"], index="group")
            if role:
                query = query.filter({"role": role})
            with cls._rdb_context():
                # TODO(move-users-to-common): pydantic validation
                query.update({"quota": quota}).run(cls._rdb_connection)

    @classmethod
    def update_group_limits(cls, group, limits):
        """_From api/libv2/api_users.py ApiUsers.UpdateGroupLimits()_"""
        category = cls.CategoryGet(group["parent_category"], True)
        # Can't update a group limits with a higher value than its category limits
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if limits and limits.get(k) and v < limits[k]:
                    raise Error(
                        "precondition_required",
                        "Can't update "
                        + group["name"]
                        + " "
                        + k
                        + " limits value with a higher value than its category limits",
                        traceback.format_exc(),
                    )

        with cls._rdb_context():
            # TODO(move-users-to-common): pydantic validation
            r.table("groups").get(group["id"]).update({"limits": limits}).run(
                cls._rdb_connection
            )

    @classmethod
    def groups_users_count(cls, groups, user_id):
        """_From api/libv2/api_users.py ApiUsers.groups_users_count()_"""
        query_groups = (
            r.table("users").get_all(r.args(groups), index="group").pluck("id")["id"]
        )
        query_secondary_groups = (
            r.table("users")
            .get_all(r.args(groups), index="secondary_groups")
            .pluck("id")["id"]
        )

        with cls._rdb_context():
            total_groups = (
                list(query_groups.run(cls._rdb_connection))
                + list(query_secondary_groups.run(cls._rdb_connection))
                + [user_id]
            )

        return len(total_groups)

    @classmethod
    def check_secondary_groups_category(cls, category, secondary_groups):
        """_From api/libv2/api_users.py ApiUsers.check_secondary_groups_category()_"""
        for group_id in secondary_groups:
            group = Caches.get_document("groups", group_id)
            if group["parent_category"] != category:
                category_name = Caches.get_document("categories", category)["name"]
                raise Error(
                    "forbidden",
                    "Group "
                    + group["name"]
                    + " does not belong to category "
                    + category_name,
                    traceback.format_exc(),
                )

    @classmethod
    def get_group_by_name_category(cls, group_name, category_id):
        """_From api/libv2/api_users.py ApiUsers.GroupGetByNameCategory()_"""
        with cls._rdb_context():
            group = list(
                r.table("groups")
                .get_all(category_id, index="parent_category")
                .filter({"name": group_name})
                .run(cls._rdb_connection)
            )
        if not group:
            raise Error(
                "not_found",
                "Not found group name " + group_name,
                traceback.format_exc(),
            )
        return group[0]

    @classmethod
    def get_users_in_group(cls, group_id: str) -> list[dict]:
        with cls._rdb_context():
            users = list(
                r.table("users")
                .get_all(group_id, index="group")
                .pluck("id", "name", "username", "photo")
                .run(cls._rdb_connection)
            )
        return users
