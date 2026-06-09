#
#   Copyright © 2025 IsardVDI
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

from fastapi import BackgroundTasks
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.domains import DomainsProcessed

# Tables allowed for term search
ALLOWED_TERM_TABLES = [
    "domains",
    "roles",
    "categories",
    "groups",
    "users",
    "media",
    "deployments",
]

# Tables that require resource unassignment on allowed update
UNASSIGN_ON_ALLOWED_UPDATE_TABLES = [
    "interfaces",
    "media",
    "reservables_vgpus",
    "boots",
    "videos",
]


class AdminAllowedsService:

    @staticmethod
    def get_table_term(table: str, data: dict, payload: dict) -> list:
        """
        Search table items by term.
        Returns matching items filtered by the user's role and category.

        Route layer constrains ``table`` to ``Literal[<ALLOWED_TERM_TABLES>]``.
        """
        data["pluck"] = ["id", "name"]

        if payload["role_id"] == "admin":
            return AdminAllowedsService._get_table_term_admin(table, data)
        else:
            return AdminAllowedsService._get_table_term_non_admin(table, data, payload)

    @staticmethod
    def _get_table_term_admin(table: str, data: dict) -> list:
        """Handle term search for admin users."""
        if table == "groups":
            return Alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=["id", "name", "parent_category", "category_name"],
                index_key="parent_category" if data.get("category") else None,
                index_value=data["category"] if data.get("category") else None,
            )
        elif table == "users":
            if data.get("exclude_role"):
                return Alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=[
                        "id",
                        "name",
                        "uid",
                        "role",
                        "category_name",
                        "group_name",
                    ],
                    query_filter=lambda u: u["role"] != data["exclude_role"],
                )
            elif data.get("category"):
                return Alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=[
                        "id",
                        "name",
                        "uid",
                        "role",
                        "category_name",
                        "group_name",
                    ],
                    index_key="category",
                    index_value=data["category"],
                )
            else:
                return Alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=[
                        "id",
                        "username",
                        "name",
                        "uid",
                        "role",
                        "category_name",
                        "group_name",
                    ],
                )
        elif table == "media":
            kind = AdminAllowedsService._resolve_media_kind(data["kind"])
            return Alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value=kind,
            )
        else:
            return Alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )

    @staticmethod
    def _get_table_term_non_admin(table: str, data: dict, payload: dict) -> list:
        """Handle term search for non-admin users (manager, etc.)."""
        if table == "roles":
            return Alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
        elif table == "categories":
            return Alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"],
                index_key="id",
                index_value=payload["category_id"],
            )
        elif table == "groups":
            return Alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=["id", "name", "parent_category", "category_name"],
                index_key="parent_category",
                index_value=payload["category_id"],
            )
        elif table == "users":
            if data.get("exclude_role"):
                return Alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "category", "uid", "role"],
                    index_key="category",
                    index_value=payload["category_id"],
                    query_filter=lambda u: u["role"] != data["exclude_role"],
                )
            else:
                return Alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "category", "uid"],
                    index_key="category",
                    index_value=payload["category_id"],
                )
        elif table == "media":
            kind = AdminAllowedsService._resolve_media_kind(data["kind"])
            # Search in the db for the term
            term_results = Alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"] + ["user", "allowed", "category"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value=kind,
            )
            # Filter if the user is allowed to see said resource
            result = []
            for element in term_results:
                if Alloweds.is_allowed(payload=payload, item=element, table="media"):
                    element.pop("allowed")
                    result.append(element)
            return result
        else:
            return Alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )

    @staticmethod
    def _resolve_media_kind(kind: str) -> str:
        """Convert frontend media kind names to database values."""
        if kind == "isos":
            return "iso"
        if kind == "floppies":
            return "floppy"
        return kind

    @staticmethod
    def update_allowed(
        table: str,
        data: dict,
        payload: dict,
        background_tasks: BackgroundTasks,
    ) -> dict:
        """
        Update the allowed access permissions for a table item.
        Handles special bastion table cases and resource unassignment.
        """
        if table == "bastion":
            AdminAllowedsService._update_bastion_allowed(
                data, payload, background_tasks
            )
        elif table == "bastion_domains":
            AdminAllowedsService._update_bastion_domains_allowed(
                data, payload, background_tasks
            )
        else:
            Alloweds.update_item_allowed_dict(table, data["id"], data["allowed"])

            if table in UNASSIGN_ON_ALLOWED_UPDATE_TABLES:
                AdminAllowedsService._handle_resource_unassignment(table, data, payload)

        return {}

    @staticmethod
    def _update_bastion_allowed(
        data: dict, payload: dict, background_tasks: BackgroundTasks
    ) -> None:
        """Update bastion allowed permissions (admin only)."""
        if payload["role_id"] != "admin":
            raise Error(
                "forbidden",
                "Only admins can update bastion alloweds",
                traceback.format_exc(),
            )
        Alloweds.update_bastion_alloweds(data["allowed"])
        # Schedule the disallowed-targets cleanup after the response.
        # Replaces the prior ``Alloweds.remove_disallowed_bastion_targets_th``
        # which fired ``gevent.spawn`` and silently never ran inside the
        # asyncio worker.
        background_tasks.add_task(Alloweds.remove_disallowed_bastion_targets)

    @staticmethod
    def _update_bastion_domains_allowed(
        data: dict, payload: dict, background_tasks: BackgroundTasks
    ) -> None:
        """Update bastion domain allowed permissions (admin only)."""
        if payload["role_id"] != "admin":
            raise Error(
                "forbidden",
                "Only admins can update bastion domain alloweds",
                traceback.format_exc(),
            )
        Alloweds.update_bastion_target_domains_alloweds(data["allowed"])
        background_tasks.add_task(Alloweds.remove_disallowed_bastion_target_domains)

    @staticmethod
    def _handle_resource_unassignment(table: str, data: dict, payload: dict) -> None:
        """Handle unassigning resources from desktops/deployments after allowed update."""
        item = data
        if not data["allowed"].get("roles") or not data["allowed"].get("categories"):
            full_row = ApiAdmin.get_table_item(table, data["id"])
            if full_row:
                full_row["allowed"].update(data["allowed"])
                item = full_row
        DomainsProcessed.unassign_resource_from_desktops_and_deployments(table, item)

    @staticmethod
    def get_allowed_table(table: str, data: dict) -> dict:
        """
        Get the allowed access list for a table item.
        Resolves the allowed field and enriches it with names.
        """
        if table == "bastion":
            return Alloweds.get_allowed(Alloweds.get_bastion_allowed_dict())
        elif table == "bastion_domains":
            return Alloweds.get_allowed(Alloweds.get_bastion_domains_allowed_dict())
        else:
            return Alloweds.get_allowed(
                Alloweds.get_item_allowed_dict(table, data["id"])
            )
