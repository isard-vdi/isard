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

from html_sanitizer import Sanitizer
from isardvdi_common.helpers.desktops_priority import MAX_SHUTDOWN_MINUTES
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.api_admin_table_defaults import apply_table_defaults

_html_sanitizer = Sanitizer()
_SANITIZE_TABLES = ("domains", "notification_tmpls", "config", "users")
# Machine-generated structured data (not user input) must not be HTML-sanitized.
# domains.xml is a libvirt XML document consumed by the engine; sanitizing it
# strips every tag and breaks domain startup.
_SANITIZE_EXCLUDE_FIELDS = {
    "domains": frozenset({"xml"}),
}


def _sanitize_table_data(table: str, data: dict) -> None:
    """Sanitize string fields in sensitive tables to prevent stored XSS."""
    if table not in _SANITIZE_TABLES:
        return
    excluded = _SANITIZE_EXCLUDE_FIELDS.get(table, frozenset())
    for key, value in data.items():
        if isinstance(value, str) and key not in excluded:
            data[key] = _html_sanitizer.sanitize(value)


from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.domains import DomainsProcessed

# Tables that require duplicate name checks
DUPLICATE_CHECK_TABLES = [
    "interfaces",
    "graphics",
    "videos",
    "qos_net",
    "qos_disk",
    "remotevpn",
    "bookings_priority",
    "desktops_priority",
]

# Tables that require resource unassignment on delete
UNASSIGN_ON_DELETE_TABLES = [
    "interfaces",
    "reservables_vgpus",
    "boots",
    "videos",
    "qos_disk",
]

# Tables that require resource unassignment on allowed update
UNASSIGN_ON_ALLOWED_UPDATE_TABLES = [
    "interfaces",
    "media",
    "reservables_vgpus",
    "boots",
    "videos",
]


def _validate_desktops_priority(table: str, data: dict) -> None:
    """Bound shutdown values: max in (0, MAX], interval time in [-MAX, -1].

    apiv3 enforced this via Cerberus; the apiv4 raw-dict path re-asserts it.
    """
    if table != "desktops_priority":
        return
    shutdown = data.get("shutdown")
    if not isinstance(shutdown, dict):
        return
    max_time = shutdown.get("max")
    if isinstance(max_time, int) and (max_time <= 0 or max_time > MAX_SHUTDOWN_MINUTES):
        raise Error(
            "bad_request",
            f"shutdown max must be between 1 and {MAX_SHUTDOWN_MINUTES} minutes",
        )
    for interval in shutdown.get("notify_intervals") or []:
        time = interval.get("time")
        if isinstance(time, int) and (time >= 0 or time < -MAX_SHUTDOWN_MINUTES):
            raise Error(
                "bad_request",
                "shutdown notify interval time must be between "
                f"{-MAX_SHUTDOWN_MINUTES} and -1 minutes",
            )


class AdminTablesService:

    @staticmethod
    def get_table(table: str, payload: dict, options: dict) -> list | dict:
        """
        Get single item or list from a table.
        Admins can access all items; managers are scoped to their category.
        """
        item_id = options.get("id")
        index = options.get("index")

        if item_id and not index:
            if payload["role_id"] == "admin":
                return ApiAdmin.admin_table_list(
                    table, id=item_id, pluck=options.get("pluck")
                )
            elif payload["role_id"] == "manager":
                return ApiAdmin.manager_table_list(
                    table,
                    payload["category_id"],
                    id=item_id,
                    pluck=options.get("pluck"),
                )
        else:
            if payload["role_id"] == "admin":
                return ApiAdmin.admin_table_list(
                    table,
                    order_by=options.get("order_by"),
                    pluck=options.get("pluck"),
                    without=options.get("without"),
                    id=item_id,
                    index=index,
                )
            elif payload["role_id"] == "manager":
                return ApiAdmin.manager_table_list(
                    table,
                    payload["category_id"],
                    order_by=options.get("order_by"),
                    pluck=options.get("pluck"),
                    without=options.get("without"),
                    id=item_id,
                    index=index,
                )

    @staticmethod
    def insert_table_item(table: str, data: dict) -> dict:
        """
        Insert a new item into a table.
        Checks for duplicate names in tables that require it.
        """
        _sanitize_table_data(table, data)
        # Apply apiv3-equivalent ``default_setter`` matrix (genuuid /
        # gensecret / mediaicon / storagepools). apiv3 ran these via
        # Cerberus' ``.normalized(data)`` before insert — the apiv4
        # port lost that pipeline, which is why every webapp ``Add``
        # modal 400'd with "Missing 'id' field in request body".
        apply_table_defaults(table, data)
        # ``apply_table_defaults`` only injects an ``id`` for tables
        # whose default_setter matrix declares ``genuuid`` (categories,
        # groups, ...). For tables where the webapp form supplies the
        # id (hypervisors, hypervisors_pools, ...), an empty body must
        # 400, not crash on ``ApiAdmin.insert_table_item``'s
        # ``data["id"]`` KeyError → generic 500. Tracked as Bug 32.
        if "id" not in data:
            raise Error("bad_request", "Missing 'id' field in request body")
        if table in DUPLICATE_CHECK_TABLES:
            if "name" not in data:
                raise Error("bad_request", "Missing 'name' field in request body")
            Helpers.check_duplicate(table, data["name"])
        _validate_desktops_priority(table, data)

        ApiAdmin.insert_table_item(table, data)
        return {}

    @staticmethod
    def update_table_item(table: str, data: dict) -> dict:
        """
        Update an existing item in a table.
        Checks for duplicate names in tables that require it.
        """
        _sanitize_table_data(table, data)
        if "id" not in data:
            raise Error("bad_request", "Missing 'id' field in request body")
        if table in DUPLICATE_CHECK_TABLES:
            if "name" not in data:
                raise Error("bad_request", "Missing 'name' field in request body")
            Helpers.check_duplicate(table, data["name"], item_id=data["id"])
        _validate_desktops_priority(table, data)

        ApiAdmin.update_table_item(table, data)
        return {}

    @staticmethod
    def delete_table_item(table: str, item_id: str) -> dict:
        """
        Delete an item from a table.
        Unassigns resources from desktops and deployments for relevant tables.
        """
        if table in UNASSIGN_ON_DELETE_TABLES:
            DomainsProcessed.unassign_resource_from_desktops_and_deployments(
                table, {"id": item_id}
            )

        ApiAdmin.delete_table_item(table, item_id)
        return {}
