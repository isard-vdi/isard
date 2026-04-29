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


from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.lib.storage.storage_pools.storage_pools import (
    StoragePoolsProcessed,
)
from rethinkdb import r

from ....helpers.desktop_events import DesktopEvents
from ....helpers.helpers import Helpers
from ....lib.users.groups.groups import GroupsProcessed
from ....models.storage_pool import StoragePool


class CategoriesProcessed(RethinkSharedConnection):

    _rdb_table = "categories"

    @classmethod
    def get_categories_frontend(cls, domain=None):
        """Get all categories for frontend usage.

        If *domain* is set and differs from the main DOMAIN env var, only
        categories whose branding domain matches are returned. Falls back to
        all frontend categories when no domain match is found.
        """
        import os

        main_domain = os.environ.get("DOMAIN")
        if domain and domain != main_domain:
            with cls._rdb_context():
                domain_matches = list(
                    r.table(cls._rdb_table)
                    .filter(
                        lambda cat: r.branch(
                            cat.has_fields({"branding": {"domain": {"enabled": True}}}),
                            cat["branding"]["domain"]["enabled"].eq(True)
                            & cat["branding"]["domain"]["name"].eq(domain),
                            False,
                        )
                    )
                    .pluck("id", "name", "frontend", "custom_url_name")
                    .order_by("name")
                    .run(cls._rdb_connection)
                )
            if domain_matches:
                return domain_matches

        with cls._rdb_context():
            categories = (
                r.table(cls._rdb_table)
                .filter({"frontend": True})
                .pluck({"id", "name", "custom_url_name"})
                .order_by("name")
                .run(cls._rdb_connection)
            )
        return list(categories)

    @classmethod
    def get_by_custom_url(cls, custom_url, domain=None):
        """Get a category by its custom URL.

        If *domain* is set and differs from the main DOMAIN env var, the lookup
        is restricted to categories whose branding domain matches.
        """
        import os

        main_domain = os.environ.get("DOMAIN")
        if domain and domain != main_domain:
            with cls._rdb_context():
                domain_matches = list(
                    r.table(cls._rdb_table)
                    .filter({"branding": {"domain": {"enabled": True, "name": domain}}})
                    .pluck("id", "name", "custom_url_name")
                    .run(cls._rdb_connection)
                )
            if domain_matches:
                if domain_matches[0].get("custom_url_name") != custom_url:
                    return None
                return {
                    "id": domain_matches[0]["id"],
                    "name": domain_matches[0]["name"],
                }

        with cls._rdb_context():
            category = list(
                r.table(cls._rdb_table)
                .filter({"custom_url_name": custom_url})
                .pluck("id", "name")
                .run(cls._rdb_connection)
            )

        if not category:
            return None

        return category[0]

    @classmethod
    def delete_category(cls, category_id, agent_id):
        """_From api/libv2/api_users.py ApiUsers.CategoryDelete()_"""
        with cls._rdb_context():
            category_media_ids = list(
                r.table("media")
                .get_all(category_id, index="category")["id"]
                .run(cls._rdb_connection)
            )
        if category_media_ids:
            Helpers.change_owner_medias(
                category_media_ids,
                Helpers.get_new_user_data("local-default-admin-admin"),
            )
        DesktopEvents.category_delete(agent_id, category_id)
        StoragePoolsProcessed.remove_category_from_storage_pool(category_id)

    @classmethod
    def update_category_quota(cls, category_id, quota, propagate, role=False):
        """_From api/libv2/api_users.py ApiUsers.UpdateCategoryQuota()_"""
        if not role:
            with cls._rdb_context():
                # TODO(move-users-to-common): pydantic validation
                r.table("categories").get(category_id).update({"quota": quota}).run(
                    cls._rdb_connection
                )
        if propagate or role:
            with cls._rdb_context():
                groups = list(
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .run(cls._rdb_connection)
                )
            for group in groups:
                GroupsProcessed.update_group_quota(
                    group, quota, propagate, role, "admin"
                )

    @classmethod
    def update_category_limits(cls, category_id, limits, propagate):
        """_From api/libv2/api_users.py ApiUsers.UpdateCategoryLimits()_"""
        with cls._rdb_context():
            r.table("categories").get(category_id).update({"limits": limits}).run(
                cls._rdb_connection
            )
        if propagate:
            with cls._rdb_context():
                r.table("groups").get_all(category_id, index="parent_category").update(
                    {"limits": limits}
                ).run(cls._rdb_connection)

    @classmethod
    def search_users_in_category(cls, category_id: str, search: str):
        with cls._rdb_context():
            return (
                r.table("users")
                .get_all(category_id, index="category")
                .filter(
                    lambda user: user["name"].downcase().match(search.lower())
                    | user["username"].downcase().match(search.lower())
                )
                .pluck("id", "name", "username")
                .run(cls._rdb_connection)
            )
